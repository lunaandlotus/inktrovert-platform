"""Inktrovert platform — Flask app factory.

"Inktrovert | Tattoo and Body Piercing Professionals Collective":
a magazine + discovery platform + professional network for the tattoo and
body piercing industry.

Blueprints (imported inside create_app so `import app` stays light):
  public     /                       magazine home, issues, stories, events,
                                     newsletter archive, search, about
  podcasts   /podcasts               series + episode listening pages
  directory  /directory              artist/studio/brand profiles + search
  claims     /claims                 find-or-create listings, claim workflow
  account    /account                register / login / logout / profile
  owner      /owner                  platform-owner dashboard (publishing,
                                     leads inbox, claim approvals, podcasts)
  support    /support                subscribe / donate / fundraise (stubs —
                                     no money moves until rails are chosen)
"""
from __future__ import annotations

import os
import sys

from flask import Flask, render_template, send_from_directory

from .config import Config
from .db import create_all, init_engine
from . import models  # noqa: F401  (register all models on Base)


def create_app(config_object=None) -> Flask:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    app = Flask(
        __name__,
        template_folder=os.path.join(root, "templates"),
        static_folder=os.path.join(root, "static"),
    )
    app.config.from_object(config_object or Config)

    init_engine(app.config["DATABASE_URL"])
    create_all()
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    from .auth import csrf_token, ensure_roles, get_current_user, init_auth
    # ensure_roles() needs flask.g -> run it inside an app context.
    with app.app_context():
        try:
            ensure_roles()
            # Seed-on-boot for ephemeral hosts (e.g. Render free tier, where
            # the SQLite file is wiped on every restart): re-seed when empty.
            # Idempotent — seed exits quietly if the owner already exists.
            # Disable with SEED_ON_BOOT=0 once a persistent database is used.
            if os.environ.get("SEED_ON_BOOT", "1") not in ("0", "", "false", "False"):
                from .db import get_db
                from .models import User
                if get_db().query(User).filter_by(email="owner@inktrovert.local").one_or_none() is None:
                    sys.path.insert(0, os.path.join(root, "scripts"))
                    import seed as _seed_module
                    _seed_module._seed()
        finally:
            from .db import close_db
            close_db()
    init_auth(app)

    # Blueprint registration (local imports: keep package import light).
    from .public import public_bp
    from .podcasts import podcast_bp
    from .directory import directory_bp
    from .claims import claims_bp
    from .account import account_bp
    from .owner import owner_bp
    from .support import support_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(podcast_bp)
    app.register_blueprint(directory_bp)
    app.register_blueprint(claims_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(owner_bp)
    app.register_blueprint(support_bp)

    @app.context_processor
    def _template_context():
        return {
            "current_user": get_current_user(),
            "csrf_token": csrf_token,
            "site_name": "Inktrovert",
            "site_full_name": "Inktrovert | Tattoo and Body Piercing Professionals Collective",
        }

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_DIR"], filename)

    @app.errorhandler(404)
    def _not_found(_exc):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def _forbidden(_exc):
        return render_template("403.html"), 403

    return app
