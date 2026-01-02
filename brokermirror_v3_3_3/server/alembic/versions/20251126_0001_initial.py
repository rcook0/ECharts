from alembic import op
import sqlalchemy as sa
revision="20251126_0001"
down_revision=None
def upgrade():
    op.create_table("users",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("email",sa.String(190),unique=True),
        sa.Column("password_hash",sa.String(255)),
        sa.Column("role",sa.String(32),server_default="user"),
        sa.Column("first_name",sa.String(120),server_default=""),
        sa.Column("last_name",sa.String(120),server_default=""),
        sa.Column("phone",sa.String(120),server_default=""),
        sa.Column("kyc_status",sa.String(32),server_default="unverified"),
        sa.Column("kyc_level",sa.Integer,server_default="0"),
        sa.Column("kyc_submitted_at",sa.BigInteger,nullable=True),
        sa.Column("kyc_verified_at",sa.BigInteger,nullable=True),
    )
    op.create_table("wallets",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),index=True),
        sa.Column("currency",sa.String(10),index=True),
        sa.Column("balance",sa.Float,server_default="0.0"),
    )
    op.create_table("transactions",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("ext_id",sa.String(64),unique=True),
        sa.Column("ts",sa.BigInteger),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),index=True),
        sa.Column("type",sa.String(16)),
        sa.Column("method",sa.String(16)),
        sa.Column("currency",sa.String(10)),
        sa.Column("amount",sa.Float),
        sa.Column("fee",sa.Float,server_default="0.0"),
        sa.Column("status",sa.String(16),server_default="pending"),
        sa.Column("reference",sa.String(64),nullable=True),
        sa.Column("instructions",sa.JSON,nullable=True),
    )
    op.create_table("kyc_uploads",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id",ondelete="CASCADE"),index=True),
        sa.Column("kind",sa.String(32)),
        sa.Column("filename",sa.String(255)),
        sa.Column("content_type",sa.String(64)),
        sa.Column("bytes",sa.Integer),
        sa.Column("sha256",sa.String(64)),
        sa.Column("ts",sa.BigInteger),
    )
    op.create_table("audit",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("ts",sa.BigInteger),
        sa.Column("evt",sa.String(64)),
        sa.Column("data",sa.Text),
    )
def downgrade():
    for t in ("audit","kyc_uploads","transactions","wallets","users"):
        op.drop_table(t)
