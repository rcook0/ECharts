from alembic import op
import sqlalchemy as sa
revision="20251201_0004"
down_revision="20251127_0003"
def upgrade():
    with op.batch_alter_table("paper_ledger") as b:
        b.add_column(sa.Column("source", sa.String(24), server_default="market"))
        b.add_column(sa.Column("reason", sa.String(64), nullable=True))
        b.add_column(sa.Column("sig", sa.String(64), nullable=True))
def downgrade():
    with op.batch_alter_table("paper_ledger") as b:
        b.drop_column("sig")
        b.drop_column("reason")
        b.drop_column("source")
