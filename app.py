import tornado.ioloop
import tornado.web
import redis
import json
from fuzzyfinder import fuzzyfinder


r = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# FIXME: courutines
class LoginHandler(tornado.web.RequestHandler):
    def get(self, user):
        # FIXME: thread-safe, session, password
        if not r.sismember('users', user):
            r.sadd('users', user)
        resp = json.dumps({'succ': True})
        self.write(resp)


class HallHandler(tornado.web.RequestHandler):
    def get(self):
        count = r.scard('users')
        users = r.srandmember('users', 10)
        resp = json.dumps({
            'count': count,
            'users': users,
        })
        self.write(resp)


class SearchHandler(tornado.web.RequestHandler):
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
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()