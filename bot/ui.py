from __future__ import annotations

import discord

__all__ = ["Paginator", "truncate"]


def truncate(text: str, limit: int) -> str:
    """Truncate text at a word boundary without exceeding ``limit`` characters."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


class Paginator(discord.ui.View):
    """Simple view with page navigation buttons."""

    def __init__(self, pages: list[discord.Embed], *, author_id: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError("Paginator requires at least one page.")
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    def current(self) -> discord.Embed:
        return self.pages[self.index]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "These buttons are not for you. Run the command yourself.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = max(0, self.index - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current(), view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
