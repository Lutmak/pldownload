import json
import os
import datetime
# import sys
# import traceback
import utils.sql as SQL
import utils.utils as U
import utils.pwsecurity as PWS
import utils.youtubemp3 as YTMP3
from flask import Flask, render_template, request, session, redirect, url_for, send_file
from socketIO_client import SocketIO, LoggingNamespace

app = Flask(__name__)
app.secret_key = "kuno secret key"
DB = None
log = None
DIRECTORY = None

@app.route("/")
def index():
    playlists = []
    if session.get('logged_in'):
        u_id = DB.get_user_id(username=session['username'])
        for pl_id, uuid in DB.get_user_playlists(iduser=u_id):
            pl = DB.get_playlist_info(idplaylist=pl_id)
            total_songs = DB.get_playlist_total_songs(uuid=uuid)
            # TOTAL NEWS se puede hacer mas eficiente
            playlists.append({
                'title': pl[0],
                'source': pl[1],
                'total': total_songs,
                'total_news': total_songs - len(DB.get_user_downloaded(iduser=u_id, idplaylist=pl_id)),
                'url1': url_for('download', uuid=uuid, fop='f', title=pl[0]),
                'url2': url_for('download', uuid=uuid, fop='p', title=pl[0]),
                'uuid': uuid
            })
    return render_template(
        'index.html',
        active_session=session.get('logged_in', False),
        username=session.get('username', None),
        user_id=session.get('user_id', None),
        playlists=playlists,
        socket_port=CONFIG['socket_port'],
        socket_host=CONFIG['socket_host'])

@app.route('/add', methods=['POST'])
def add_user():
    if DB.insert_user(username=request.form['username'], password=PWS.get_hashed_password(request.form['password'].encode('utf-8')).decode(), email=request.form['email']):
        log.write("{}\tUsuario nuevo añadido {}\n".format(datetime.datetime.now(), request.form['username']))
        session['logged_in'] = True
        session['username'] = request.form['username']
        return ('', 204)
    return ('', 400)

@app.route('/insertpl', methods=['POST'])
def insertpl():
    # try:
        log.write("{} INSERT PL \n")
        user = session['username']
        playlist = request.form['plurl']
        u_id = DB.get_user_id(username=user)
        log.write("{} user: {}\tplaylist {}\n".format(datetime.datetime.now(), user, playlist))
        print(playlist)
        log.write(playlist+"\n")

        if 'youtu' in playlist:
            source = 'youtube'
            title = U.get_yt_playlist_title(playlist)
        elif 'spotify' in playlist:
            source = 'spotify'
            print("getting Token...")
            token = YTMP3.get_sp_token()
            print("getting playlist data...")
            playlist_data = U.get_sp_playlist_data(playlist)
            spotify_user = playlist_data['user']
            listaid = playlist_data['idplaylist']
            title = YTMP3.get_sp_tracklist_name(token=token, user=spotify_user, listaid=listaid)
        else:
            return ('', 400)

        if DB.insert_playlist(title, playlist, source):
            log.write("Playlist {} Insertada\n".format(playlist))

        pl_id = DB.get_playlists_id(url=playlist)[0]
        if DB.add_playlist_to_user(iduser=u_id, idplaylist=pl_id):
            log.write("Playlist {} linkeada con usuario {}\n".format(pl_id, u_id))

        uuid = DB.get_uuid(iduser=u_id, idplaylist=pl_id)
        pl_directory = DIRECTORY + uuid
        U.crate_dir(pl_directory)

        print("Scrapping playlist...")
        if source == 'youtube':
            for song_id in DB.scrap_youtube_playlist(url=playlist, uuid=uuid):
                print(song_id)
        else:
            for song_id in DB.scrap_spotify_playlist(token=token, spotify_user=spotify_user, listaid=listaid, uuid=uuid):
                print(song_id)
        print("Finished")
        return ('', 200)
    # except:
    #     return ('', 400)

@app.route('/delete', methods=['POST'])
def delete_playlist():
    uuid = request.form['uuid']
    DB.delete_playlist(uuid=uuid)
    return('', 200)

@app.route('/update', methods=['POST'])
def update():
    # try:
        uuid = request.form['uuid']
        log.write("{}\t Update {}\n".format(datetime.datetime.now(), uuid))
        pl_id = DB.get_playlists_id(uuid=uuid)[0]
        pl_info = DB.get_playlist_url_source_user(idplaylist=pl_id)
        old_pl_ids = set(DB.get_songs_id_from_uuid(uuid=uuid))
        new_pl_ids = set()

        if pl_info[1] == 'youtube':
            for song_id in DB.scrap_youtube_playlist(url=pl_info[0], uuid=uuid, need_id=True):
                new_pl_ids.add(song_id)
        else:
            token = YTMP3.get_sp_token()
            playlist_data = U.get_sp_playlist_data(pl_info[0])
            spotify_user = playlist_data['user']
            listaid = playlist_data['idplaylist']
            for song_id in DB.scrap_spotify_playlist(token=token, spotify_user=spotify_user, listaid=listaid, uuid=uuid):
                new_pl_ids.add(song_id)

        # already_downloaded_ids = set(DB.get_user_downloaded(iduser=pl_info[2], idplaylist=pl_id))
        deleted_songs = old_pl_ids - new_pl_ids
        for s in deleted_songs:
            DB.delete_song(idsong=s)
        return ('', 200)
    # except:
    #     return ('', 400)

@app.route('/dl/<uuid>', methods=['GET', 'POST'])
def download(uuid):
    log.write("{}\t Download {}\n".format(datetime.datetime.now(), uuid))
    fop = request.args.get('fop')
    title = U.prepare_string_for_file(request.args.get('title'))
    pl_id = DB.get_playlists_id(uuid=uuid)[0]
    user_id = DB.get_user_id(uuid=uuid)
    pl_directory = DIRECTORY + uuid
    U.crate_dir(pl_directory)
    if fop == 'p':
        log.write("{}\t partial {}\n".format(datetime.datetime.now(), pl_id))
        set1 = set(DB.get_songs_id_from_uuid(uuid=uuid))
        set2 = set(DB.get_user_downloaded(iduser=user_id, idplaylist=pl_id))
        set3 = set1 - set2
    elif fop == 'f':
        log.write("{}\t full {}\n".format(datetime.datetime.now(), pl_id))
        set3 = set(DB.get_songs_id_from_uuid(uuid=uuid))
    else:
        return ('', 400)

    total_songs = len(set3)

    with open("{}.m3u".format(os.path.join(pl_directory, title)), "w+") as playlist_file, SocketIO(CONFIG['socket_host'], CONFIG['socket_port'], LoggingNamespace) as socket:
        socket.emit('push_info', {'info': {'status': 'STARTED'}, 'user_id': str(user_id)+'_'+uuid})
        for song, i in zip(set3, range(total_songs)):
            s_info = DB.get_song_info(songid=song)
            link_descarga = YTMP3.get_dl_link_ytmp3org(id_video=s_info[0])
            if "ERROR" not in link_descarga:
                YTMP3.download_song(filepath=pl_directory, id_video=s_info[0], mp3name=U.prepare_string_for_file(s_info[1]), link=link_descarga)
                DB.add_user_downloaded(iduser=user_id, idsong=song, idplaylist=pl_id)
                playlist_file.write("{}.mp3\n".format(U.prepare_string_for_file(s_info[1])))
                log.write("DESCARGADA songId {}\tu_id {}\tpl_id {}\tdir {}\n".format(song, user_id, pl_id, pl_directory))
                print("DESCARGADA {0} de {1}".format(i+1, total_songs))
                socket.emit(
                    'push_info',
                    {
                        'info': {
                            'status': 'OK',
                            'total': total_songs,
                            'c': i+1
                        },
                        'user_id': str(user_id)+'_'+uuid
                    })
            else:
                DB.insert_error(idsong=song, description="No se pudo descargar")
                log.write("ERROR songId {}\tu_id {}\tpl_id {}\tdir {}\n".format(song, user_id, pl_id, pl_directory))
                print("ERROR songId {}\tu_id {}\tpl_id {}\tdir {}\n".format(song, user_id, pl_id, pl_directory))
                socket.emit('push_info', {'info': {'status': 'ERROR', 'songname': s_info[1]}, 'user_id': str(user_id)+'_'+uuid})
        socket.emit('push_info', {'info': {'status': 'FINISHED'}, 'user_id': str(user_id)+'_'+uuid})

    log.write("{} Creando Comprimido {}, {}\n".format(datetime.datetime.now(), pl_id, "FULL" if fop == 'f' else "PARTIAL"))
    U.create_zip(folder_uuid=pl_directory, file_name=DIRECTORY + title)
    U.delete_files(pl_directory)
    return send_file(filename_or_fp="{}.zip".format(DIRECTORY + title), mimetype="application/zip", as_attachment=True)

@app.route('/freedownload', methods=['POST'])
def freedownload():
    # try:
        temp_id = request.form['temp_id']
        playlist_url = request.form['playlist_url']
        log.write("{} user: {} playlist{}".format(datetime.datetime.now(), None, playlist_url))
        uuid = U.gen_uuid()
        pl_directory = DIRECTORY + uuid
        U.crate_dir(pl_directory)
        if 'youtu' in playlist_url:
            title = U.get_yt_playlist_title(playlist_url)
            total_songs = U.count_youtube_playlist(playlist_url)
            with open("{}.m3u".format(os.path.join(pl_directory, title)), "w+") as playlist_file, SocketIO(CONFIG['socket_host'], CONFIG['socket_port'], LoggingNamespace) as socket:
                socket.emit('push_info', {'info': {'status': 'STARTED'}, 'user_id': temp_id})
                for (idyt, name), i in zip(U.scrap_youtube_playlist_anon(url=playlist_url), range(total_songs)):
                    link_descarga = YTMP3.get_dl_link_ytmp3org(id_video=idyt)
                    if "ERROR" not in link_descarga:
                        mp3name = U.prepare_string_for_file(name)
                        YTMP3.download_song(filepath=pl_directory, id_video=idyt, mp3name=mp3name, link=link_descarga)
                        playlist_file.write("{}.mp3".format(mp3name))
                        print("DESCARGADA {0} de {1}".format(i+1, total_songs))
                        log.write("DESCARGADA IDYT {}\tdir {}\n".format(idyt, pl_directory))
                        socket.emit(
                            'push_info',
                            {
                                'info': {
                                    'status': 'OK',
                                    'total': total_songs,
                                    'c': i+1
                                },
                                'user_id': temp_id
                            })
                    else:
                        print("ERROR IDYT {}".format(idyt, pl_directory))
                        log.write("DESCARGADA IDYT {}\n".format(idyt, pl_directory))
                        socket.emit('push_info', {'info': {'status': 'ERROR', 'songname': name}, 'user_id': temp_id})
                socket.emit('push_info', {'info': {'status': 'FINISHED'}, 'user_id': temp_id})

        elif 'spotify' in playlist_url:
            print("getting Token...")
            token = YTMP3.get_sp_token()
            print("getting playlist data...")
            playlist_data = U.get_sp_playlist_data(playlist_url)
            spotify_user = playlist_data['user']
            listaid = playlist_data['idplaylist']
            title = YTMP3.get_sp_tracklist_name(token=token, user=spotify_user, listaid=listaid)
            total_songs = U.count_spotify_playlist(token=token, spotify_user=spotify_user, listaid=listaid)
            with open("{}.m3u".format(os.path.join(pl_directory, title)), "w+") as playlist_file, SocketIO(CONFIG['socket_host'], CONFIG['socket_port'], LoggingNamespace) as socket:
                socket.emit('push_info', {'info': {'status': 'STARTED'}, 'user_id': temp_id})
                for (idyt, name), i in zip(U.scrap_spotify_playlist_anon(token=token, spotify_user=spotify_user, listaid=listaid), range(total_songs)):
                    link_descarga = YTMP3.get_dl_link_ytmp3org(id_video=idyt)
                    if "ERROR" not in link_descarga:
                        mp3name = U.prepare_string_for_file(name)
                        YTMP3.download_song(filepath=pl_directory, id_video=idyt, mp3name=mp3name, link=link_descarga)
                        playlist_file.write("{}.mp3".format(mp3name))
                        print("DESCARGADA {0} de {1}".format(i+1, total_songs))
                        log.write("DESCARGADA IDYT {}\tdir {}\n".format(idyt, pl_directory))
                        socket.emit(
                            'push_info',
                            {
                                'info': {
                                    'status': 'OK',
                                    'total': total_songs,
                                    'c': i+1
                                },
                                'user_id': temp_id
                            })
                    else:
                        print("ERROR IDYT {}".format(idyt, pl_directory))
                        log.write("DESCARGADA IDYT {}\n".format(idyt, pl_directory))
                        socket.emit('push_info', {'info': {'status': 'ERROR', 'songname': name}, 'user_id': temp_id})
                socket.emit('push_info', {'info': {'status': 'FINISHED'}, 'user_id': temp_id})

        log.write("{} Creando Comprimido {}\n".format(datetime.datetime.now(), 'ANON'))
        U.create_zip(folder_uuid=pl_directory, file_name=pl_directory)
        U.delete_files(pl_directory)
        return (uuid, 200)
        # return send_file(filename_or_fp="{}.zip".format(DIRECTORY + title), mimetype="application/zip", as_attachment=True)
    # except:
    #     return ('', 400)
@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        user = request.form['login_email']
        if PWS.check_password(plain_text_password=request.form['login_password'], hashed_password=DB.get_user_pw(username=user)):
            iduser = DB.get_user_id(username=user if "@" not in user else None, email=user if "@" in user else None)
            session['logged_in'] = True
            session['username'] = DB.get_username(iduser=iduser)
            session['user_id'] = iduser
            return ('', 200)
        return ('', 400)
    except:
        log.write("{}\tError desconocido en Login para usuario {}\n".format(datetime.datetime.now(), request.form.get('login_email')))
        return ('', 400)

@app.route('/report', methods=['POST'])
def report():
    try:
        DB.insert_error(
            description=request.form['description'],
            iduser=request.form['user_id'],
            playlist=request.form['playlist'],
            songname=request.form['songname'])
        return('', 200)
    except:
        return ('', 400)

@app.route('/changepw', methods=['POST'])
def changepw():
    if PWS.check_password(plain_text_password=request.form['oldpw'], hashed_password=DB.get_user_pw(iduser=request.form['user_id'])):
        print("PW coinciden")
        DB.change_user_pw(iduser=request.form['user_id'], password=PWS.get_hashed_password(request.form['newpw'].encode('utf-8')).decode())
        log.write("{}\tUsuario {} cambio su contraseña\n".format(datetime.datetime.now(), request.form['user_id']))
        return ('', 200)
    else:
        return ('', 400)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))


@app.route('/getzip/<uuid>', methods=['GET', 'POST'])
def get_zip(uuid):
    print("UUID"+uuid)
    return send_file(filename_or_fp="{}.zip".format(DIRECTORY + uuid), mimetype="application/zip", as_attachment=True)

@app.route('/check_username', methods=['POST'])
def check_valid_username():
    if DB.get_user_id(username=request.form['username']):
        return ('', 400)
    return ('', 204)

@app.route('/check_email', methods=['POST'])
def check_valid_email():
    if DB.get_user_id(email=request.form['email']):
        return ('', 400)
    return ('', 204)

if __name__ == "__main__":
    log = open("log.txt", 'a+')
    CONFIG = json.load(open("config.json", "r"))
    CONNECTION = CONFIG['connection']
    DB = SQL.Connection(CONNECTION['driver'], CONNECTION['server'], CONNECTION['database'], CONNECTION['user'], CONNECTION['password'])
    DIRECTORY = CONFIG['directory2']
    app.run(host='0.0.0.0', debug=False, threaded=True)
    # while(True):
    #     try:
    #         app.run(host='0.0.0.0')
    #     except Exception as e:
    #         log.write("ERROR DESCONOCIDO")
    #         traceback.format_exc(file=log)
