from alembic import op
import sqlalchemy as sa
revision="20251127_0003"
down_revision="20251127_0002"
def upgrade():
    op.create_table("paper_accounts",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),unique=True,index=True),
        sa.Column("cash_usd",sa.Float,server_default="100000.0"),
        sa.Column("peak_equity",sa.Float,server_default="100000.0"),
        sa.Column("created_at",sa.BigInteger),
    )
    op.create_table("paper_ledger",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),index=True),
        sa.Column("ts",sa.BigInteger),
        sa.Column("kind",sa.String(24)),
        sa.Column("symbol",sa.String(32),nullable=True),
        sa.Column("qty",sa.Float,nullable=True),
        sa.Column("price",sa.Float,nullable=True),
        sa.Column("realized",sa.Float,server_default="0.0"),
        sa.Column("cash_delta",sa.Float,server_default="0.0"),
        sa.Column("note",sa.String(255),nullable=True),
    )
def downgrade():
    for t in ("paper_ledger","paper_accounts"):
        op.drop_table(t)
