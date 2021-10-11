from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from discord import Embed


@Bloxlink.command
class AboutCommand(Bloxlink.Module):
    """learn about Bloxlink!"""

    def __init__(self):
        self.aliases = ["bloxlink"]
        self.dm_allowed    = True
        self.slash_enabled = True
        self.slash_only = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        locale   = CommandArgs.locale
        prefix   = CommandArgs.prefix

        embed = Embed(title=locale("commands.about.title"))

        embed.add_field(name=locale("commands.about.embed.title"), value=f"**{locale('commands.about.embed.field_1.line_1', prefix=prefix)}**\n{locale('commands.about.embed.field_1.line_2')}"
                                                                         f"\n\n{locale('commands.about.embed.field_1.line_3')}", inline=False)


        embed.add_field(name=locale("commands.about.embed.field_2.title"), value=f"[{locale('commands.about.embed.field_2.line_1')}](https://blox.link/support)",
                        inline=False)

        embed.set_thumbnail(url=Bloxlink.user.avatar.url)


        await response.send(embed=embed)
