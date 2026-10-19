from .models import Job
from . import greenhouse, lever, ashby

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

__all__ = ["Job", "ADAPTERS", "greenhouse", "lever", "ashby"]
