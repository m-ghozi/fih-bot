from __future__ import annotations

from typing import Awaitable, Callable

import discord

__all__ = ["Paginator", "Picker", "truncate"]

MAX_OPTIONS = 25


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


class _PickerSelect(discord.ui.Select):
    def __init__(self, picker: "Picker") -> None:
        self.picker = picker
        super().__init__(
            placeholder="Choose an option…", options=self._page_options()
        )
        self._update_placeholder()

    def _page_options(self) -> list[discord.SelectOption]:
        start = self.picker.page * MAX_OPTIONS
        chunk = self.picker.options[start : start + MAX_OPTIONS]
        return [
            discord.SelectOption(label=truncate(label, 100), value=value)
            for label, value in chunk
        ]

    def _update_placeholder(self) -> None:
        total = len(self.picker.options)
        if total <= MAX_OPTIONS:
            self.placeholder = self.picker.placeholder
            return
        start = self.picker.page * MAX_OPTIONS
        end = min(start + MAX_OPTIONS, total)
        self.placeholder = (
            f"{self.picker.placeholder} ({start + 1}-{end} of {total})"
        )

    def show_page(self, page: int) -> None:
        self.picker.page = page
        self.options = self._page_options()
        self._update_placeholder()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self.picker.on_pick(self.values[0])
        if embed is None:
            await interaction.edit_original_response(
                content=f"Could not load **{self.values[0]}**.",
                embed=None,
                view=None,
            )
            return
        await interaction.edit_original_response(embed=embed, view=None)


class Picker(discord.ui.View):
    """Paginated dropdown that replaces itself with the chosen item's embed."""

    def __init__(
        self,
        options: list[tuple[str, str]],
        *,
        author_id: int,
        on_pick: Callable[[str], Awaitable[discord.Embed | None]],
        placeholder: str = "Choose an option…",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        if not options:
            raise ValueError("Picker requires at least one option.")
        self.options = options
        self.author_id = author_id
        self.on_pick = on_pick
        self.placeholder = placeholder
        self.page = 0
        self.message: discord.Message | None = None
        self.select = _PickerSelect(self)
        self.add_item(self.select)

        self.previous: discord.ui.Button | None = None
        self.next: discord.ui.Button | None = None
        if len(options) > MAX_OPTIONS:
            self.previous = discord.ui.Button(
                label="Previous", style=discord.ButtonStyle.secondary
            )
            self.previous.callback = self._previous_page
            self.next = discord.ui.Button(
                label="Next", style=discord.ButtonStyle.secondary
            )
            self.next.callback = self._next_page
            self.add_item(self.previous)
            self.add_item(self.next)
            self._sync_buttons()

    def _page_count(self) -> int:
        return (len(self.options) + MAX_OPTIONS - 1) // MAX_OPTIONS

    def _sync_buttons(self) -> None:
        if self.previous is None or self.next is None:
            return
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self._page_count() - 1

    async def _change_page(
        self, interaction: discord.Interaction, delta: int
    ) -> None:
        page = min(max(self.page + delta, 0), self._page_count() - 1)
        self.select.show_page(page)
        self._sync_buttons()
        await interaction.response.edit_message(view=self)

    async def _previous_page(self, interaction: discord.Interaction) -> None:
        await self._change_page(interaction, -1)

    async def _next_page(self, interaction: discord.Interaction) -> None:
        await self._change_page(interaction, 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This menu belongs to someone else. Run the command yourself.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
