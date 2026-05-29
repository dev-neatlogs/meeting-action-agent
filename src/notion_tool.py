import os
from typing import List, Type

from crewai.tools import BaseTool
from notion_client import Client
from pydantic import BaseModel, Extra, Field


class ActionItem(BaseModel):
    title: str = Field(default="Untitled Action Item")
    owner: str = Field(default="Unassigned")
    deadline: str = Field(default="TBD")
    priority: str = Field(default="Medium")

    class Config:
        extra = Extra.allow


class NotionToolInput(BaseModel):
    action_items: List[ActionItem] = Field(
        description=(
            "A list of action item objects describing title (str), owner (str), "
            "deadline (str), and priority (str). Additional fields are allowed and "
            "passed through to Notion."
        )
    )


class NotionTool(BaseTool):
    name: str = "notion_publisher"
    description: str = (
        "Creates action item entries in a Notion database. The tool accepts a list "
        "of action item objects and publishes each one—title (str), owner (str), "
        "deadline (str), and priority (str) are normalized before persistence."
    )
    args_schema: Type[BaseModel] = NotionToolInput

    def _run(self, action_items: List[ActionItem]) -> str:
        if not action_items:
            return "No action items provided."

        results = [self._publish_item(item) for item in action_items]
        return "\n".join(results)

    def _publish_item(self, item: ActionItem) -> str:
        try:
            title = item.title or "Untitled Action Item"
            owner = item.owner or "Unassigned"
            deadline = item.deadline or "TBD"
            priority = item.priority or "Medium"

            priority_map = {"high": "High", "medium": "Medium", "low": "Low"}
            priority = priority_map.get(priority.lower(), "Medium")

            notion = Client(auth=os.environ["NOTION_TOKEN"])
            database_id = os.environ["NOTION_DATABASE_ID"]

            children = [
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"Owner: {owner}"}}
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"Deadline: {deadline}"}}
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"Priority: {priority}"}}
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "Status: Not Started"}}
                        ]
                    },
                },
            ]

            properties: dict = {
                "Name": {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            }

            page = notion.pages.create(
                parent={"database_id": database_id},
                properties=properties,
                children=children,
            )

            page_id = page.get("id", "unknown")
            return (
                f"Successfully created Notion page for: '{title}' "
                f"(owner: {owner}, deadline: {deadline}, priority: {priority}). "
                f"Page ID: {page_id}"
            )
        except Exception as exc:
            return f"Error creating Notion page: {str(exc)}"
