from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Text, String, DateTime, Integer, ForeignKey, func, UniqueConstraint
from pgvector.sqlalchemy import Vector
import shortuuid
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(22), primary_key=True, default=shortuuid.uuid)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(22), primary_key=True, default=shortuuid.uuid)
    repo_id: Mapped[str] = mapped_column(String(22), ForeignKey("repos.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    last_indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("repo_id", "file_path"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(22), primary_key=True, default=shortuuid.uuid)
    repo_id: Mapped[str] = mapped_column(String(22), ForeignKey("repos.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    function_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )