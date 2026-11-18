"""GJ Academy Phase 1: local-only demonstration, never a broker integration."""
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
# Ephemeral by default: restarting the demo signs users out.
app.secret_key = os.environ.get('GJ_DEMO_SECRET', os.urandom(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')


def protected(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('student'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('email', '').strip().lower() == 'student@gjacademy.com' and request.form.get('password') == 'Demo@123':
            session.clear()
            session['student'] = 'Alex Morgan'
            session.permanent = bool(request.form.get('remember'))
            return redirect(url_for('page', name='strategies'))
        return render_template('login.html', error='Email or password does not match the demo account.'), 401
    if session.get('student'):
        return redirect(url_for('page', name='strategies'))
    return render_template('login.html')


@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/<name>')
@protected
def page(name):
    allowed = {'dashboard', 'strategies', 'strategy_details', 'subscribe', 'trading', 'orders', 'analytics', 'settings'}
    if name not in allowed:
        return 'Page not found', 404
    return render_template(name + '.html', page=name, student=session['student'])


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
