var http = require('http');
var express = require('express'),
    app = module.exports.app = express();

var server = http.createServer(app);
var io = require('socket.io').listen(server);

server.listen(999);

app.get('/webclient', function (req, res) {
    res.sendfile(__dirname + '/web.html');
});

app.get('/mobile', function (req, res) {
    res.sendfile(__dirname + '/mobile.html');
});

io.sockets.on('connection', function (socket) {
//      socket.emit('pop', { hello: 'world' });
	console.log('NUEVO SOCKET CONECTADO');
    socket.on('push_info', function (data) {
        socket.broadcast.emit('room_'+data.user_id, data.info);
    });
});