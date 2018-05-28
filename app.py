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
define("redis_host", default='localhost', help="redis host", type=str)



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
            logging.info("User login: %s", user)
        if not r.hget('room', user):
            room = {
                'master': user,
                'partner': None,
                'state': 'waiting',
            }
            r.hset('room', user, json.dumps(room))
            logging.info("Room set: %s", room)
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

    def open(self):
        if r.hget('room', 'user1') and r.hget('room', 'user2'):
            r.hdel('room', 'user1', 'user2', 'touch_loc1', 'touch_loc2')
        GameHandler.waiters.add(self)
        logging.info("WebSocket opened")

    @classmethod
    def send_updates(cls, chat):
        logging.info("sending message to %d waiters", len(cls.waiters))
        for waiter in cls.waiters:
            try:
                waiter.write_message(chat)
            except:
                logging.error("Error sending message", exc_info=True)

    def on_message(self, message):
        message = json.loads(message)
        method = message.get('method', None)
        if method == 'init':
            if not r.hget('room', 'user1'):
                r.hset('room', 'user1', message['user'])
            elif not r.hget('room', 'user2') and r.hget('room', 'user1') != message['user']:
                r.hset('room', 'user2', message['user'])
            else:
                self.write_message('Init failed')
            GameHandler.send_updates(json.dumps({
                'method': 'init',
                'user1': r.hget('room', 'user1'),
                'user2': r.hget('room', 'user2'),
            }))

        elif method == 'play':
            touch_role = message['touch_role']
            r.hset('room', touch_role, json.dumps(message['touch_loc']))
            touch_loc1 = r.hget('room', 'touch_loc1')
            touch_loc2 = r.hget('room', 'touch_loc2')
            if touch_loc1 and touch_loc2:
                GameHandler.send_updates(json.dumps({
                    'method': 'play',
                    'touch_loc1': json.loads(touch_loc1),
                    'touch_loc2': json.loads(touch_loc2),
                }))
        else:
            pass


    def on_close(self):
        GameHandler.waiters.remove(self)
        logging.info("WebSocket closed")


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