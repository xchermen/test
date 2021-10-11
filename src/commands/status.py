from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import GOLD_COLOR # pylint: disable=import-error, no-name-in-module
from discord import Embed


get_features = Bloxlink.get_module("premium", attrs=["get_features"])


@Bloxlink.command
class StatusCommand(Bloxlink.Module):
    """view your Bloxlink premium status"""

    def __init__(self):
        self.examples = ["@justin"]
        self.arguments = [{
            "prompt": "Please specify the user to view the status of.",
            "name": "user",
            "type": "user",
            "optional": True
        }]
        self.category = "Premium"
        self.free_to_use = True
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_only = True

    async def __main__(self, CommandArgs):
        user = CommandArgs.parsed_args.get("user") or CommandArgs.author
        response = CommandArgs.response

        embed = Embed()
        embed.set_author(name=user, icon_url=user.avatar.url)

        profile, transfer_to = await get_features(user)

        attributes, features = profile.attributes, profile.features
        has_premium = features.get("premium")

        if has_premium:
            embed.add_field(name="Premium Status", value="Active")
            embed.colour = GOLD_COLOR

            if attributes.get("selly"):
                embed.add_field(name="Expiry", value=profile.days == 0 and "Never (unlimited)" or f"**{profile.days}** days left")
            elif attributes.get("patreon"):
                amount_cents = profile.amount_cents
                dollars = int(amount_cents / 100)
                cents_left = amount_cents % 100

                if cents_left < 10:
                    cents_left = "0" + str(cents_left)

                embed.add_field(name="Amount Pledged", value=f"${dollars}.{cents_left}")

        else:
            embed.description = f"This user does not have premium. They may donate [here](https://patreon.com/bloxlink)."

        if profile.features:
            embed.add_field(name="Features", value=", ".join(profile.features.keys()))

        if profile.notes:
            embed.add_field(name="Notes", value="\n".join(profile.notes), inline=False)

        if transfer_to:
            embed.add_field(name="Transferring To ID", value=transfer_to)


        await response.send(embed=embed)
