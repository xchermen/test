from contextlib import redirect_stdout
import textwrap
import io
from discord import Embed
from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..constants import RED_COLOR, INVISIBLE_COLOR # pylint: disable=import-error, no-name-in-module

# Adapted from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py

@Bloxlink.module
class EvalM(Bloxlink.Module):
	def __init__(self):
		self._last_result = None

	def cleanup_code(self, content):
		"""Automatically removes code blocks from the code."""
		# remove ```py\n```
		if content.startswith('```') and content.endswith('```'):
			return '\n'.join(content.split('\n')[1:-1])

		# remove `foo`
		return content.strip('` \n')

	async def __call__(self, code, message=None, env=None, codeblock=True):
		env = env or {}

		load_env = {
			"client": self.client,
			"channel": message and message.channel,
			"author": message and message.author,
			"guild": message and message.guild,
			"message": message,
			"r": self.r,
			"redis": self.redis,
			"cache": self.cache,
			"_": self._last_result
		}

		load_env.update(globals())
		load_env.update(env)

		body = self.cleanup_code(code)
		stdout = io.StringIO()

		to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

		try:
			exec(to_compile, load_env)
		except Exception as e:
			description = codeblock and f"```js\n{e.__class__.__name__}: {e}```" or f"{e.__class__.__name__}: {e}"

			embed = Embed(
				title="Evaluation Error",
				description=description,
				color=RED_COLOR
			)

			return embed

		func = load_env['func']

		try:
			with redirect_stdout(stdout):
				ret = await func()

		except Exception as e:
			value = stdout.getvalue()
			description = codeblock and f"```js\n{e.__class__.__name__}: {e}```" or f"{e.__class__.__name__}: {e}"

			embed = Embed(
				title="Evaluation Error",
				description=description,
				color=RED_COLOR
			)

			return embed

		else:
			value = stdout.getvalue()

			if ret is None:
				if value:
					description = codeblock and f"```py\n{value[0:2000]}```" or value[0:2000]

					embed = Embed(
						title="Evaluation Result",
						description=description,
						color=INVISIBLE_COLOR
					)

					return embed
			else:
				self._last_result = ret
				description = codeblock and f"```py\n{value}{str(ret)[0:2000]}```" or f"{value}{str(ret)[0:2000]}"

				embed = Embed(
					title="Evaluation Result",
					description=description,
					color=INVISIBLE_COLOR
				)

				return embed
