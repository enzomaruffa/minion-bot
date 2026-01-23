from typing import Optional

from src.db import get_session
from src.db.models import ItemPriority, ShoppingListType
from src.db.queries import (
    check_shopping_item,
    clear_checked_items,
    create_shopping_item,
    delete_shopping_item,
    get_contact_by_name,
    get_gifts_by_contact,
    get_shopping_item,
    list_shopping_items,
)


# Keywords for auto-inference
GIFT_KEYWORDS = {"gift", "present", "birthday", "christmas", "anniversary", "for mom", "for dad", "for him", "for her"}
WISHLIST_KEYWORDS = {"wish", "want", "someday", "dream", "would love", "maybe", "eventually", "save up"}
GROCERY_KEYWORDS = {"grocery", "groceries", "milk", "bread", "eggs", "cleaning", "toilet", "soap", "food", "fruit", "vegetable", "meat", "cheese"}


def _infer_list_type(item: str, recipient: Optional[str] = None) -> ShoppingListType:
    """Auto-infer the list type based on item text and recipient."""
    item_lower = item.lower()

    # Has recipient -> Gifts
    if recipient:
        return ShoppingListType.GIFTS

    # Check keywords
    for keyword in GIFT_KEYWORDS:
        if keyword in item_lower:
            return ShoppingListType.GIFTS

    for keyword in WISHLIST_KEYWORDS:
        if keyword in item_lower:
            return ShoppingListType.WISHLIST

    for keyword in GROCERY_KEYWORDS:
        if keyword in item_lower:
            return ShoppingListType.GROCERIES

    # Default to Groceries
    return ShoppingListType.GROCERIES


def _get_list_emoji(list_type: ShoppingListType) -> str:
    """Get the emoji for a list type."""
    emojis = {
        ShoppingListType.GIFTS: "🎁",
        ShoppingListType.GROCERIES: "🛒",
        ShoppingListType.WISHLIST: "✨",
    }
    return emojis.get(list_type, "📝")


def add_to_list(
    item: str,
    list_type: Optional[str] = None,
    notes: Optional[str] = None,
    recipient: Optional[str] = None,
    priority: Optional[str] = None,
) -> str:
    """Add an item to a shopping list.

    Args:
        item: The item to add (e.g., "milk", "gift for Jana: a book").
        list_type: Optional list type (gifts/groceries/wishlist). Auto-inferred if not provided.
        notes: Optional notes about the item.
        recipient: Optional recipient name (for gifts). Auto-links to contact if found.
        priority: Priority (low/medium/high). Defaults to medium.

    Returns:
        Confirmation message with the created item ID.
    """
    session = get_session()

    # Determine list type
    if list_type:
        try:
            lt = ShoppingListType(list_type.lower())
        except ValueError:
            session.close()
            return f"Invalid list type '{list_type}'. Use: gifts, groceries, or wishlist."
    else:
        lt = _infer_list_type(item, recipient)

    # Parse priority
    prio = ItemPriority.MEDIUM
    if priority:
        try:
            prio = ItemPriority(priority.lower())
        except ValueError:
            pass

    # Try to resolve recipient to a contact
    contact_id = None
    recipient_display = recipient
    if recipient:
        contact = get_contact_by_name(session, recipient)
        if contact:
            contact_id = contact.id
            recipient_display = contact.name  # Use canonical name

    shopping_item = create_shopping_item(
        session,
        list_type=lt,
        name=item,
        notes=notes,
        recipient=recipient if not contact_id else None,  # Only store text if no contact link
        contact_id=contact_id,
        priority=prio,
    )
    session.close()

    emoji = _get_list_emoji(lt)
    recipient_info = f" (for {recipient_display})" if recipient_display else ""
    return f"Added to {emoji} {lt.value.title()}: #{shopping_item.id} {item}{recipient_info}"


def show_list(list_type: Optional[str] = None, include_checked: bool = False) -> str:
    """Show shopping list items grouped by list type.

    Args:
        list_type: Optional filter by list type (gifts/groceries/wishlist). Shows all if not provided.
        include_checked: If True, also show checked items. Default False.

    Returns:
        Formatted list of items grouped by list type.
    """
    session = get_session()

    lt = None
    if list_type:
        try:
            lt = ShoppingListType(list_type.lower())
        except ValueError:
            session.close()
            return f"Invalid list type '{list_type}'. Use: gifts, groceries, or wishlist."

    items = list_shopping_items(session, lt, include_checked=include_checked)
    session.close()

    if not items:
        if lt:
            return f"No items in {_get_list_emoji(lt)} {lt.value.title()} list."
        return "All shopping lists are empty."

    # Group by list type
    grouped: dict[ShoppingListType, list] = {}
    for item in items:
        item_type = item.shopping_list.list_type
        if item_type not in grouped:
            grouped[item_type] = []
        grouped[item_type].append(item)

    lines = []
    for item_type in [ShoppingListType.GIFTS, ShoppingListType.GROCERIES, ShoppingListType.WISHLIST]:
        if item_type not in grouped:
            continue

        emoji = _get_list_emoji(item_type)
        lines.append(f"\n{emoji} **{item_type.value.title()}**")

        for item in grouped[item_type]:
            checkbox = "☑️" if item.checked else "⬜"
            # Show contact name if linked, otherwise fallback to recipient text
            if item.contact:
                recipient_info = f" (for {item.contact.name})"
            elif item.recipient:
                recipient_info = f" (for {item.recipient})"
            else:
                recipient_info = ""
            notes_info = f" - {item.notes}" if item.notes else ""
            lines.append(f"  {checkbox} #{item.id}: {item.name}{recipient_info}{notes_info}")

    return "\n".join(lines).strip()


def check_item(item_id: int) -> str:
    """Mark a shopping item as checked (purchased/done).

    Args:
        item_id: The ID of the item to check.

    Returns:
        Confirmation message or error.
    """
    session = get_session()
    item = get_shopping_item(session, item_id)
    if not item:
        session.close()
        return f"Item #{item_id} not found."

    name = item.name
    success = check_shopping_item(session, item_id, checked=True)
    session.close()

    if success:
        return f"☑️ Checked off: #{item_id} {name}"
    return f"Failed to check item #{item_id}."


def uncheck_item(item_id: int) -> str:
    """Mark a shopping item as unchecked.

    Args:
        item_id: The ID of the item to uncheck.

    Returns:
        Confirmation message or error.
    """
    session = get_session()
    item = get_shopping_item(session, item_id)
    if not item:
        session.close()
        return f"Item #{item_id} not found."

    name = item.name
    success = check_shopping_item(session, item_id, checked=False)
    session.close()

    if success:
        return f"⬜ Unchecked: #{item_id} {name}"
    return f"Failed to uncheck item #{item_id}."


def remove_item(item_id: int) -> str:
    """Remove an item from a shopping list.

    Args:
        item_id: The ID of the item to remove.

    Returns:
        Confirmation message or error.
    """
    session = get_session()
    item = get_shopping_item(session, item_id)
    if not item:
        session.close()
        return f"Item #{item_id} not found."

    name = item.name
    success = delete_shopping_item(session, item_id)
    session.close()

    if success:
        return f"Removed item #{item_id}: {name}"
    return f"Failed to remove item #{item_id}."


def clear_checked(list_type: Optional[str] = None) -> str:
    """Clear all checked items from shopping lists.

    Args:
        list_type: Optional list type to clear (gifts/groceries/wishlist). Clears all if not provided.

    Returns:
        Confirmation message with count of removed items.
    """
    session = get_session()

    lt = None
    if list_type:
        try:
            lt = ShoppingListType(list_type.lower())
        except ValueError:
            session.close()
            return f"Invalid list type '{list_type}'. Use: gifts, groceries, or wishlist."

    count = clear_checked_items(session, lt)
    session.close()

    if count == 0:
        return "No checked items to clear."

    list_info = f" from {_get_list_emoji(lt)} {lt.value.title()}" if lt else ""
    return f"Cleared {count} checked item(s){list_info}."


def show_gifts_for_contact(contact_name: str, include_checked: bool = False) -> str:
    """Show all gift ideas for a specific contact.

    Args:
        contact_name: The name (or alias) of the contact.
        include_checked: If True, also show checked items. Default False.

    Returns:
        List of gift ideas for the contact.
    """
    session = get_session()

    contact = get_contact_by_name(session, contact_name)
    if not contact:
        session.close()
        return f"Contact '{contact_name}' not found."

    gifts = get_gifts_by_contact(session, contact.id)
    session.close()

    if not gifts:
        return f"No gift ideas saved for {contact.name}."

    # Filter checked if needed
    if not include_checked:
        gifts = [g for g in gifts if not g.checked]
        if not gifts:
            return f"No unchecked gift ideas for {contact.name}."

    lines = [f"🎁 **Gift ideas for {contact.name}:**"]
    for item in gifts:
        checkbox = "☑️" if item.checked else "⬜"
        notes_info = f" - {item.notes}" if item.notes else ""
        lines.append(f"  {checkbox} #{item.id}: {item.name}{notes_info}")

    return "\n".join(lines)
