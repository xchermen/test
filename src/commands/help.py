from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error
from discord import File
from io import BytesIO

fetch = Bloxlink.get_module("utils", attrs=["fetch"])

@Bloxlink.command
class HelpCommand(Bloxlink.Module):
    """view information about Bloxlink"""

    def __init__(self):
        self.dm_allowed    = True
        self.slash_enabled = True

        self.images = None
        self.urls = [
            "https://i.imgur.com/zQwITet.png",
            "https://i.imgur.com/yv6jfNC.png",
            "https://i.imgur.com/pwMB8wZ.png"
        ]

    async def __setup__(self):
        self.images = []

        for url in self.urls:
            image_data, image_response = await fetch(url=url, bytes=True, raise_on_failure=False)

            if image_response.status == 200:
                self.images.append(image_data)

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        prefix   = CommandArgs.prefix
        channel  = CommandArgs.channel
        guild    = CommandArgs.guild

        if CommandArgs.slash_command or (guild and not channel.permissions_for(guild.me).attach_files):
            urls = "\n".join(self.urls)
            await response.send(f"Some general info is below! To view all commands, say `{prefix}commands`.\n{urls}")
        else:
            await response.send(f"Some general info is below! To view all commands, say `{prefix}commands`.", files=[File(BytesIO(b), filename=f"image_{i}.png") for i, b in enumerate(self.images)])