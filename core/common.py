import nextcord

from .config import clist


def is_admin(member: nextcord.Member) -> bool:
    if member.guild.owner_id == member.id:
        return True
    admin_roles = clist("server", "admins", fallback=[])
    return any(r.name.lower() in [a.lower() for a in admin_roles] for r in member.roles)


VALID_TZ = {
    "UTC",
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "Europe/London",
    "Europe/Amsterdam",
    "Europe/Budapest",
    "Europe/Berlin",
    "Europe/Paris",
    "Europe/Bucharest",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Australia/Sydney",
    "America/Sao_Paulo",
}

