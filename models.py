from sqlalchemy import Column, Integer, String, Date, Time
from db import Base

class Cita(Base):
    __tablename__ = "citas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=True)
    telefono = Column(String(20), index=True, nullable=False)
    especialidad = Column(String(100), nullable=True)
    fecha = Column(Date, nullable=False)
    hora = Column(Time, nullable=False)
    estado = Column(String(20), default="agendada")
