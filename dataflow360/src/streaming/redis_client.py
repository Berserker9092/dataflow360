"""Connexion Redis partagée (étape 47)."""

import os

import redis

from src import config  # noqa: F401


def get_redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )
