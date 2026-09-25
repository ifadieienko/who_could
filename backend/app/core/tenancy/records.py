"""core / tenancy / records domain. Legacy API behavior is preserved."""

from fastapi import HTTPException
from sqlalchemy import select


def scoped(s, cls, id, a):
    x = s.scalar(select(cls).where(cls.id == id, cls.workshop_id == a.workshop_id))
    if not x:
        raise HTTPException(404, "Запись не найдена")
    return x

