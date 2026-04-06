
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("dashboard_updates", self.channel_name)
        print(f"✅ Dashboard WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("dashboard_updates", self.channel_name)

    async def new_ticket(self, event):
        """Send new ticket notification to connected clients"""
        await self.send(text_data=json.dumps({
            'type': 'new_ticket',
            'control_no': event['control_no'],
            'message': event['message'],
            'new_count': event.get('new_count', 0),
        }))