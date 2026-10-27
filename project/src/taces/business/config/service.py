"""Administrator policy changes preserve each course's spent privacy budget."""

from decimal import Decimal

from taces.business.auth.policy import require_permission
from taces.business.common import write_audit
from taces.business.errors import ServiceError
from taces.business.timezone import utc_stamp


RANGES = {"epsilon": {"min": .01, "max": 1.0}, "k": {"min": 3, "max": 50},
          "epsilonTotal": {"min": .1, "max": 20.0}}
UNITS = {"epsilon": "ε", "k": "份", "epsilonTotal": "ε"}


def invalid_value(field, message="参数超出范围或格式不合法。"):
    return ServiceError(422, "INVALID_VALUE", message, field=field)


def micros(value, field):
    if type(value) not in (int, float, Decimal):
        raise invalid_value(field)
    amount = Decimal(str(value))
    bounds = RANGES[field]
    if not amount.is_finite() or not Decimal(str(bounds["min"])) <= amount <= Decimal(str(bounds["max"])):
        raise invalid_value(field)
    if amount != amount.quantize(Decimal(".000001")):
        raise invalid_value(field, "隐私预算最多支持六位小数。")
    return int(amount * 1_000_000)


def config_payload(row):
    return {"values": {"epsilon": row["epsilon_micros"] / 1_000_000, "k": row["threshold"],
                       "epsilonTotal": row["total_micros"] / 1_000_000}, "ranges": RANGES, "units": UNITS}


class ConfigService:
    def __init__(self, database, auth):
        self.database = database
        self.auth = auth

    def get(self, token):
        with self.auth._operation(token, "privacy.read") as (con, actor):
            require_permission(actor, "privacy:configure")
            return config_payload(con.execute("SELECT * FROM main.privacy_policy WHERE singleton=1").fetchone())

    def update(self, token, body):
        with self.auth._operation(token, "privacy.configure", write=True) as (con, actor):
            require_permission(actor, "privacy:configure")
            if not isinstance(body, dict) or not body:
                raise invalid_value("request")
            for key in body:
                if key not in RANGES:
                    raise invalid_value(key, "未知配置字段。")
            old = con.execute("SELECT * FROM main.privacy_policy WHERE singleton=1").fetchone()
            epsilon = micros(body["epsilon"], "epsilon") if "epsilon" in body else old["epsilon_micros"]
            total = micros(body["epsilonTotal"], "epsilonTotal") if "epsilonTotal" in body else old["total_micros"]
            k = body.get("k", old["threshold"])
            if type(k) is not int or not 3 <= k <= 50:
                raise invalid_value("k")
            if epsilon > total:
                raise invalid_value("epsilon", "单次发布费用不能超过每课预算总量。")
            if "epsilonTotal" in body:
                spent = con.execute("SELECT coalesce(max(eps_used_micros),0) FROM main.budget_ledger").fetchone()[0]
                if total < spent:
                    raise invalid_value("epsilonTotal", "预算总量不能低于任一课程已消费的金额。")
                con.execute("UPDATE main.budget_ledger SET eps_total_micros=?,updated_at=?", (total, utc_stamp()))
            changed = epsilon != old["epsilon_micros"] or k != old["threshold"]
            con.execute("UPDATE main.privacy_policy SET epsilon_micros=?,threshold=?,total_micros=?,revision=revision+? WHERE singleton=1",
                        (epsilon, k, total, int(changed)))
            write_audit(con, actor["user_id"], "privacy.configure")
            return config_payload(con.execute("SELECT * FROM main.privacy_policy WHERE singleton=1").fetchone())
