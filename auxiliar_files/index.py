import json
import os
import datetime
import utils.sql as SQL
import utils.dbfunctions as DB
import utils.utils as U
import utils.youtubemp3 as YTMP3

CONFIG = ""
CONNECTION = ""
PLAYLISTS = []
USER = ""
DIRECTORY = "C:/"

def download_logged_in():
    connection = SQL.Connection(CONNECTION['driver'], CONNECTION['server'], CONNECTION['database'], CONNECTION['user'], CONNECTION['password'])
    cursor = connection.cursor
    u_id = DB.get_user_id(cursor=cursor, username=USER)[0]
    for playlist in PLAYLISTS:
        log.write("{} user: {}\tplaylist {}\n".format(datetime.datetime.now(), USER, playlist))
        print(playlist)
        log.write(playlist)

        if 'youtu' in playlist:
            source = 'youtube'
            title = U.get_yt_playlist_title(playlist)
        else:
            source = 'spotify'
            print("getting Token...")
            token = YTMP3.get_sp_token()
            print("getting playlist data...")
            playlist_data = U.get_sp_playlist_data(playlist)
            spotify_user = playlist_data['user']
            listaid = playlist_data['idplaylist']
            title = YTMP3.get_sp_tracklist_name(token=token, user=spotify_user, listaid=listaid)

        if DB.insert_playlist(cursor, title, playlist, source):
            print("Playlist {} Insertada".format(playlist))
            log.write("Playlist {} Insertada".format(playlist))

        pl_id = DB.get_playlists_id(cursor=cursor, url=playlist)[0]
        if DB.add_playlist_to_user(cursor=cursor, iduser=u_id, idplaylist=pl_id):
            print("Playlist {} linkeada con usuario {}".format(pl_id, u_id))
            log.write("Playlist {} linkeada con usuario {}".format(pl_id, u_id))

        uuid = DB.get_uuid(cursor=cursor, iduser=u_id, idplaylist=pl_id)[0]
        pl_directory = DIRECTORY + uuid
        U.crate_dir(pl_directory)

        print("Scrapping playlist...")
        if source == 'youtube':
            DB.scrap_youtube_playlist(cursor=cursor, url=playlist, idplaylist=pl_id)
        else:
            DB.scrap_spotify_playlist(cursor=cursor, token=token, spotify_user=spotify_user, listaid=listaid, idplaylist=pl_id)
        set1 = set(DB.get_songs_id(cursor=cursor, idplaylist=pl_id))
        set2 = set(DB.get_user_downloaded(cursor=cursor, iduser=u_id, idplaylist=pl_id))
        set3 = set1 - set2
        print("Finished scrapping playlist, starting Download")

        for song in set3:
            s_info = DB.get_song_info(cursor=cursor, songid=song)
            link_descarga = YTMP3.get_dl_link_ytmp3org(id_video=s_info[0])
            if "ERROR" not in link_descarga:
                YTMP3.download_song(filepath=pl_directory, id_video=s_info[0], mp3name=U.prepare_string_for_file(s_info[1]), link=link_descarga)
                DB.add_user_downloaded(cursor, iduser=u_id, idsong=song, idplaylist=pl_id)
                print("DESCARGADA songId {}\tu_id {}\tpl_id {}\tdir {}".format(song, u_id, pl_id, pl_directory))
                log.write("DESCARGADA songId {}\tu_id {}\tpl_id {}\tdir {}".format(song, u_id, pl_id, pl_directory))
            else:
                DB.insert_error(cursor=cursor, idsong=song, description="No se pudo descargar")
                print("ERROR songId {}\tu_id {}\tpl_id {}\tdir {}".format(song, u_id, pl_id, pl_directory))
                log.write("ERROR songId {}\tu_id {}\tpl_id {}\tdir {}".format(song, u_id, pl_id, pl_directory))

        # Se ve muy ineficiente
        print("Writing playlist file")
        with open("{}.m3u".format(os.path.join(pl_directory, U.prepare_string_for_file(title))), "w+") as playlist_file:
            for idsong in DB.get_user_downloaded(cursor=cursor, iduser=u_id, idplaylist=pl_id):
                playlist_file.write("{}.mp3\n".format(U.prepare_string_for_file(DB.get_song_info(cursor=cursor, songid=idsong)[1])))

def download_anon(playlist_url):
    log.write("{} user: {} playlist{}".format(datetime.datetime.now(), None, playlist_url))
    pl_arr = []
    U.scrap_youtube_playlist_anon(url=playlist_url, arr=pl_arr)
    pl_directory = DIRECTORY + U.gen_uuid()
    U.crate_dir(pl_directory)
    with open("{}.m3u".format(U.prepare_string_for_file(title)), "w+") as playlist_file:
        for idyt, name in pl_arr:
            link_descarga = YTMP3.get_dl_link_ytmp3org(id_video=idyt)
            if "ERROR" not in link_descarga:
                mp3name = U.prepare_string_for_file(name)
                YTMP3.download_song(filepath=pl_directory, id_video=idyt, mp3name=mp3name, link=link_descarga)
                playlist_file.write("{}.mp3".format(mp3name))
                print("DESCARGADA IDYT {}\tdir {}".format(idyt, pl_directory))
                log.write("DESCARGADA IDYT {}\tdir {}".format(idyt, pl_directory))
            else:
                print("DESCARGADA IDYT {}\tdir {}".format(idyt, pl_directory))
                log.write("DESCARGADA IDYT {}\tdir {}".format(idyt, pl_directory))

if __name__ == "__main__":
    log = open("log.txt", 'a+')
    CONFIG = json.load(open("config.json", "r"))
    CONNECTION = CONFIG['connection']
    PLAYLISTS = CONFIG['playlists']
    USER = CONFIG['user']
    download_logged_in() if USER else download_anon(playlist_url)
