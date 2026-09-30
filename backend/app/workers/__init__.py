"""Long-lived background loops that keep the email-account factory running.

Two of them, with a deliberate split of responsibility:

- proxy_refresher    - owns the proxy pool. Re-scrapes every configured free
                       source every 2 minutes and replaces the free part of the
                       list with the result. Nothing else in the system scrapes
                       on a schedule.
- pipeline_scheduler - owns the pipelines. Keeps N (default 7) signup pipelines
                       in flight, each with its own identity and its own proxy
                       taken from whatever the refresher last put in the pool;
                       when one finishes it starts another.

Started/stopped via app.routers.workers, and the refresher is started
automatically from main.py's lifespan (see the note there about why the
scheduler isn't).

The singletons are aliased privately below so importing this package doesn't
rebind `app.workers.pipeline_scheduler` / `app.workers.proxy_refresher` from
the submodules to the instances inside them - import the instances from their
own modules.
"""
from app.workers.pipeline_scheduler import pipeline_scheduler as _pipeline_scheduler
from app.workers.proxy_refresher import proxy_refresher as _proxy_refresher

WORKERS = {
    _proxy_refresher.name: _proxy_refresher,
    _pipeline_scheduler.name: _pipeline_scheduler,
}

__all__ = ["WORKERS"]
