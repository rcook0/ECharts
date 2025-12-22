from alembic import op
import sqlalchemy as sa
revision="20251127_0002"
down_revision="20251126_0001"
def upgrade():
    op.create_table("paper_trades",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),index=True),
        sa.Column("ts",sa.BigInteger),
        sa.Column("symbol",sa.String(32),index=True),
        sa.Column("side",sa.String(4)),
        sa.Column("qty",sa.Float),
        sa.Column("price",sa.Float),
    )
def downgrade():
    op.drop_table("paper_trades")
