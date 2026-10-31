from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect


def record(entity, exclude=()):
    return jsonable_encoder(
        {
            attr.key: getattr(entity, attr.key)
            for attr in inspect(entity).mapper.column_attrs
            if attr.key not in exclude
        }
    )
