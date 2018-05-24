import logging
import tornado.ioloop
import tornado.web
import redis
import json
from tornado.options import define, options
from fuzzyfinder import fuzzyfinder

define("port", default=8888, help="run on the given port", type=int)
define("host", default='0.0.0.0', help="run on the given host", type=str)
define("redis_port", default=6379, help="redis port", type=int)
define("redis_host", default='localhost', help="redis host", type=str)



r = redis.StrictRedis(host=options.redis_host, port=options.redis_port, db=0, decode_responses=True)


class BaseHandler(tornado.web.RequestHandler):

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.set_header("Access-Control-Allow-Headers", "access-control-allow-origin,authorization,content-type")

    def options(self, *args):
        self.set_status(204)
        self.finish()

# FIXME: courutines
class LoginHandler(BaseHandler):

    def get(self, user):
        # FIXME: thread-safe, session, password
        if not r.sismember('users', user):
            r.sadd('users', user)
        resp = json.dumps({'succ': True})
        logging.info("User login: %s", user)
        self.write({'succ': True})


class HallHandler(BaseHandler):
    def get(self):
        count = r.scard('users')
        users = r.srandmember('users', 10)
        resp = json.dumps({
            'count': count,
            'users': users,
        })
        self.write(resp)


class SearchHandler(BaseHandler):
    def get(self, user):
        users = r.smembers('users')
        found_users = list(fuzzyfinder(user, list(users)))
        resp = json.dumps(found_users)
        self.write(resp)


# FIXME: use websocket
class InviteHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("hello world")



class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("hello world")


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login/(.*)", LoginHandler),
        (r"/hall", HallHandler),
        (r"/search/(.*)", SearchHandler),
        (r"/invite/(.*)", InviteHandler),
    ])

if __name__ == "__main__":
    tornado.options.parse_command_line()
    app = make_app()
    app.listen(options.port, address=options.host)
    tornado.ioloop.IOLoop.current().start()