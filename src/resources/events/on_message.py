from ..structures import Bloxlink, Arguments # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module

parse_message = Bloxlink.get_module("commands", attrs="parse_message")


@Bloxlink.module
class MessageEvent:
	def __init__(self):
		pass

	async def __setup__(self):
		@Bloxlink.event
		async def on_message(message):
			author = message.author

			if (author.bot or not message.channel or Arguments.in_prompt(author)) or (message.guild and message.guild.unavailable):
				return

			try:
				await parse_message(message)
			except CancelCommand:
				pass
