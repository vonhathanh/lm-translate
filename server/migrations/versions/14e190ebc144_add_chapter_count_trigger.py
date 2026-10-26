"""add chapter count trigger

Revision ID: 14e190ebc144
Revises: 861a45f31f90
Create Date: 2026-10-26 10:19:14.868502

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14e190ebc144'
down_revision: Union[str, Sequence[str], None] = '861a45f31f90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE OR REPLACE FUNCTION update_book_chapter_count()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE book
                SET chapter_count = chapter_count + 1
                WHERE id = NEW.book_id;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE book
                SET chapter_count = chapter_count - 1
                WHERE id = OLD.book_id;
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER chapter_count_trigger
        AFTER INSERT OR DELETE ON chapter
        FOR EACH ROW
        EXECUTE FUNCTION update_book_chapter_count();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS chapter_count_trigger ON chapter")
    op.execute("DROP FUNCTION IF EXISTS update_book_chapter_count()")
