"""Leitura de segredos/parametros AWS com cache em memoria (vive o tempo do container)."""

from functools import cache

import boto3


def parse_allowlist(value: str) -> frozenset[int]:
    """'123, 456' -> {123, 456}. Itens vazios sao ignorados; lixo nao numerico e erro."""
    return frozenset(int(item) for item in value.split(",") if item.strip())


@cache
def get_secret(secret_id: str) -> str:
    client = boto3.client("secretsmanager")
    return str(client.get_secret_value(SecretId=secret_id)["SecretString"])


@cache
def get_parameter(name: str) -> str:
    client = boto3.client("ssm")
    return str(client.get_parameter(Name=name)["Parameter"]["Value"])
