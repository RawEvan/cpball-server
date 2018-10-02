import logging
import tornado.ioloop
import tornado.web
import tornado.websocket
import redis
import json
from ast import literal_eval
from tornado.options import define, options
from fuzzyfinder import fuzzyfinder

define("port", default=8888, help="run on the given port", type=int)
define("host", default='0.0.0.0', help="run on the given host", type=str)
define("redis_port", default=6379, help="redis port", type=int)
define("redis_host", default='127.0.0.1', help="redis host", type=str)

logging.getLogger().setLevel(logging.INFO)

r = redis.StrictRedis(host=options.redis_host, port=options.redis_port, db=0, decode_responses=True)


class BaseWebSocketHandler(tornado.websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

class BaseRequestHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.set_header("Access-Control-Allow-Headers", "access-control-allow-origin,authorization,content-type")

    def options(self, *args):
        self.set_status(204)
        self.finish()

# FIXME: courutines
class LoginHandler(BaseRequestHandler):

    def get(self, user):
        # FIXME: thread-safe, session, password
        if not r.sismember('users', user):
            r.sadd('users', user)
            logging.info("User added to queue: %s", user)
        resp = json.dumps({'succ': True})
        self.write(resp)


class HallHandler(BaseWebSocketHandler):
    def open(self):
        print("WebSocket opened")

    def on_message(self, message):
        message = json.loads(message)
        method = message.get('method', None)
        if method == 'invite':
            user = message.get('user', None)
            partner = message.get('partner', None)
            if not user or not partner or not r.sismember('users', user) or not r.sismember('users', partner):
                resp = json.dumps({'method': 'invite', 'succ': False})
                self.write(resp)
            room = literal_eval(r.hget('room', user))
            room['partner'] = partner
            r.hset('room', user, json.dumps(room))
            resp = json.dumps({'method': 'init', 'succ': True, 'room': room})
            self.write_message(resp)

    def on_close(self):
        print("WebSocket closed")


class GameHandler(BaseWebSocketHandler):
    waiters = set()

    def __init__(self, application, request, **kwargs):
        self.user = None
        self.room = None
        super(GameHandler, self).__init__(application, request, **kwargs)

    def open(self):
        GameHandler.waiters.add(self)
        logging.info("WebSocket opened")

    @classmethod
    def send_broadcast(cls, msg, room, log=True):
        waiters = [w for w in cls.waiters if w.room == room]
        for waiter in waiters:
            try:
                waiter.write_message(msg)
                if log:
                    logging.info("sending broadcast to %s", waiter.user)
            except:
                logging.error("Error sending broadcast", exc_info=True)

    @classmethod
    def set_waiter_room(cls, user, room):
        for w in cls.waiters:
            if w.user == user:
                w.room = room
                break

    def init_room(self, message):
        user = message.get('sender')
        # debug
        if message.get('debug') and not user:
            user = str(r.scard('users') + 1)
            message['sender'] = user
            if not r.sismember('users', user):
                r.sadd('users', '1')
                logging.info("User added to queue: %s", user)

        self.user = user
        users = r.sscan('users')[1]
        other_users = [u for u in users if u != user]
        master = other_users and other_users[0]
        # insert server message
        message['server'] = {
            'user1': master,
            'user2': user,
            'room': master,
            'owner': master,
        }
        if master:
            # set the first user as the master and the room key
            r.hset('room', master, user)
            logging.info("Room created: %s, %s", master, user)
            r.srem('users', master)
            logging.info("User removed from queue: %s", master)
            r.srem('users', user)
            logging.info("User removed from queue: %s", user)

            message['server']['method'] = 'start'
            self.room = master
            GameHandler.set_waiter_room(master, self.room)
            GameHandler.send_broadcast(json.dumps(message), self.room)
        else:
            message['server']['method'] = 'init'
            self.write_message(json.dumps(message))
            logging.info("sending message to %s", user)


    def play(self, message):
        room = message.get('room')
        # FIXME
        message['server'] = {
            'method': 'play',
            'user1': '1',
            'user2': '2',
            'owner': '1',
            'room': room,
        }
        # TODO: members' data will only be sent to owner,
        # while onwer's data sent to all members
        GameHandler.send_broadcast(message, room, log=True)

    def on_message(self, message):
        """
        
        :param message: 
        e.g.:
        {
            'sender': '1',
            // client event (current client state)
            'event': 'init',
            'room': '1',
            'server': {
                'method': 'start',
                'user1': '1',
                'user2': '2',
                'owner': '1',
                'room': '1',
            },
            'client': {
                '1': { //uid
                    'name': '1',
                    'touch_loc': this.touchLoc,
                },
                '2': {
                    'name': '2',
                }
            },
            'food': {
                'location': this.touchLoc,
            }
        };
        :return: 
        """
        message = json.loads(message)
        event = message.get('event', None)
        if event == 'init':
            self.init_room(message)
        elif event == 'play':
            self.play(message)
        else:
            pass


    def on_close(self):
        GameHandler.waiters.remove(self)
        if r.hdel('room', self.user):
            logging.info("Room closed: %s" % self.user)
            result = {
                'method': 'stop',
            }
            GameHandler.send_broadcast(json.dumps(result), self.room)
        if r.sismember('users', self.user):
            r.srem('users', self.user)
            logging.info("User logout: %s" % self.user)


def make_app():
    return tornado.web.Application([
        (r"/login/(.*)", LoginHandler),
        (r"/hall", HallHandler),
        (r"/game", GameHandler),
    ])

if __name__ == "__main__":
    tornado.options.parse_command_line()
    app = make_app()
    logging.info('Listen on %s:%s' % (options.host, options.port))
    app.listen(options.port, address=options.host)
    tornado.ioloop.IOLoop.current().start()
