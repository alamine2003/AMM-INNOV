"""Réponses d'erreur de l'API quand une dépendance manque (campagne de chaos, s02a/s02e).

Pool PostgreSQL saturé, base injoignable, requête interrompue par statement_timeout ou
lock_timeout : l'API renvoyait une page HTML « Server Error (500) ». Le client reçoit
désormais un 503 JSON avec Retry-After, qui dit « réessayez », pas « bogue ».
"""

import logging

from django.db import InterfaceError, OperationalError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)


class StorageUnavailable(APIException):
    """Stockage des scans injoignable : 503 explicite plutôt qu'un 500 (s10a, s10c)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Le stockage des scans est momentanément indisponible. Réessayez plus tard."
    default_code = "storage_unavailable"


class StoredFileLost(APIException):
    """Fichier absent du stockage : lot déposé avant le stockage permanent (disque éphémère).

    410 et code explicite, plutôt qu'un 503 « réessayez » qui ne réussira jamais.
    """

    status_code = status.HTTP_410_GONE
    default_detail = (
        "Fichier perdu (stocké avant la mise en place du stockage permanent) : "
        "réimportez ce dossier."
    )
    default_code = "file_lost"


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None and isinstance(exc, OperationalError | InterfaceError):
        logger.error("Base de données indisponible ou saturée : %s", exc)
        set_rollback()
        response = Response(
            {"detail": "Service momentanément indisponible, réessayez dans quelques secondes."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "5"},
        )
    return response
