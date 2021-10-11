import math
from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import SHARD_RANGE, CLUSTER_ID, STARTED, IS_DOCKER, RELEASE # pylint: disable=import-error, no-name-in-module
from discord import Embed
from time import time
from psutil import Process
from os import getpid

broadcast = Bloxlink.get_module("ipc", attrs="broadcast")



@Bloxlink.command
class StatsCommand(Bloxlink.Module):
    """view the current stats of Bloxlink"""

    def __init__(self):
        self.aliases = ["statistics", "nerdinfo"]
        self.dm_allowed = True
        self.slash_enabled = True

        if len(SHARD_RANGE) > 1:
            self.shard_range = f"{SHARD_RANGE[0]}-{SHARD_RANGE[len(SHARD_RANGE)-1]}"
        else:
            self.shard_range = SHARD_RANGE[0]

    async def __main__(self, CommandArgs):
        response = CommandArgs.response

        clusters  = 0
        total_mem = 0

        process = Process(getpid())
        process_mem = math.floor(process.memory_info()[0] / float(2 ** 20))

        if IS_DOCKER:
            total_guilds = guilds = 0
            total_mem = 0
            errored = 0

            stats = await broadcast(None, type="STATS")
            clusters = len(stats)

            for cluster_id, cluster_data in stats.items():
                if cluster_data in ("cluster offline", "cluster timeout"):
                    errored += 1
                else:
                    total_guilds += cluster_data[0]
                    total_mem += cluster_data[1]

            if errored:
                guilds = f"{total_guilds} ({len(self.client.guilds)}) ({errored} errored)"
            else:
                guilds = f"{total_guilds} ({len(self.client.guilds)})"

        else:
            total_guilds = guilds = str(len(self.client.guilds))
            clusters = 1
            total_mem = process_mem

        seconds = math.floor(time() - STARTED)

        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        days, hours, minutes, seconds = None, None, None, None

        if d:
            days = f"{d}d"
        if h:
            hours = f"{h}h"
        if m:
            minutes = f"{m}m"
        if s:
            seconds = f"{s}s"

        uptime = f"{days or ''} {hours or ''} {minutes or ''} {seconds or ''}".strip()
        mem = IS_DOCKER and f"{total_mem} ({process_mem})" or process_mem

        embed = Embed(description=f"Roblox Verification made easy! Features everything you need to integrate your Discord server with Roblox.")
        embed.set_author(name=Bloxlink.user.name, icon_url=Bloxlink.user.avatar.url)

        embed.add_field(name="Servers", value=guilds)
        embed.add_field(name="Node Uptime", value=uptime)
        embed.add_field(name="Memory Usage", value=f"{mem} MB")

        embed.add_field(name="Resources", value="**[Website](https://blox.link)** | **[Discord](https://blox.link/support)** | **[Invite Bot]"
                             "(https://blox.link/invite)** | **[Premium](https://blox.link/premium)**\n\n**[Repository](https://github.com/bloxlink/Bloxlink)**",
                             inline=False)

        embed.set_footer(text=f"Shards: {self.shard_range} | Node: {CLUSTER_ID}{'/'+(str(clusters-1)) if clusters > 1 else ''}")

        await response.send(embed=embed)

        if IS_DOCKER and RELEASE == "MAIN":
            await self.r.table("miscellaneous").insert({
                "id": "stats",
                "stats": {
                    "guilds": total_guilds,
                    "memory": total_mem,
                    "uptime": uptime,
                    "clusters": clusters
                }

            }, conflict="update").run()
