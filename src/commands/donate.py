from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import LIMITS # pylint: disable=import-error, no-name-in-module
import discord

PREMIUM_PERKS = "\n".join([
    f"- More role bindings allowed (from {LIMITS['BINDS']['FREE']} to {LIMITS['BINDS']['PREMIUM']}).",
    f"- `persistRoles:` update users as they type once every 2 hours",
    f"- Access to the `Pro` version of Bloxlink - a bot in less servers, so downtime is very minimal.",
     "- Customize the name and profile picture of bot responses (`{prefix}whitelabel`).",
     "- Set an age limit that checks the person's Roblox account age. (`{prefix}settings change agelimit`).",
     "- Customize the name of Magic Roles (`{prefix}magicroles`).",
     "- No cooldown on some commands.",
     "- More restrictions (`{prefix}restrict`) " + f"allowed (from {LIMITS['RESTRICTIONS']['FREE']} to {LIMITS['RESTRICTIONS']['PREMIUM']}).",
     "- More groups allowed to be added to your Group-Lock (`{prefix}grouplock`).",
     "- And more! Check `{prefix}settings change` to view the premium settings."
])


@Bloxlink.command
class DonateCommand(Bloxlink.Module):
    """learn how to receive Bloxlink Premium"""

    def __init__(self):
        self.aliases = ["premium"]
        self.dm_allowed = True
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        prefix = CommandArgs.prefix

        embed = discord.Embed(title="Bloxlink Premium")
        embed.description = "We appreciate all donations!\nBy donating a certain amount, you will receive **[Bloxlink Premium](https://www.patreon.com/join/bloxlink?)** " \
                            f"on __every server you own__ and receive these perks:\n{PREMIUM_PERKS.format(prefix=prefix)}" \

        embed.add_field(name="Frequently Asked Questions", value="1.) Can I transfer premium to someone else?\n"
                                                                f"> Yes, use the `{prefix}transfer` command. "
                                                                 "You'll be able to disable the transfer whenever you want "
                                                                f"with `{prefix}transfer disable`.\n"
                                                                 "2.) How do I receive my perks after donating?\n"
                                                                 "> Link your Discord account to Patreon. After, wait 15-20 "
                                                                 "minutes and your perks should be activated. Feel free to ask "
                                                                 "in our support server if you need more help: <https://blox.link/support>.", inline=False)

        embed.set_footer(text="Powered by Bloxlink", icon_url=Bloxlink.user.avatar.url)

        view = discord.ui.View()
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Click to Subscribe ($6)", url="https://www.patreon.com/join/bloxlink?"))

        await response.send(embed=embed, view=view)
