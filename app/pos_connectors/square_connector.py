"""
Square POS Connector stub.
Will integrate with Square API when credentials are available.
"""

from .base import BasePOSConnector


class SquareConnector(BasePOSConnector):
    """Connector for Square POS system."""
    
    API_BASE_URL = "https://connect.squareup.com/v2"
    
    def __init__(self, credentials):
        super().__init__(credentials)
        self.location_id = credentials.get('location_id')
    
    def fetch_checks(self, bar, start_date, end_date):
        """
        Fetch orders from Square API.
        
        Square API endpoint: POST /orders/search
        Requires: location_ids, date range in query
        
        For now, returns empty list (stub implementation).
        """
        # TODO: Implement actual Square API call
        # Example:
        # headers = {
        #     'Authorization': f'Bearer {self.access_token}',
        #     'Content-Type': 'application/json'
        # }
        # body = {
        #     'location_ids': [self.location_id],
        #     'query': {
        #         'filter': {
        #             'date_time_filter': {
        #                 'closed_at': {
        #                     'start_at': start_date.isoformat(),
        #                     'end_at': end_date.isoformat()
        #                 }
        #             }
        #         }
        #     }
        # }
        # response = requests.post(
        #     f'{self.API_BASE_URL}/orders/search',
        #     headers=headers,
        #     json=body
        # )
        return []
    
    def test_connection(self):
        """Test Square API credentials."""
        # TODO: Make a simple API call to verify credentials
        return {'success': False, 'error': 'Not implemented'}
    
    def refresh_access_token(self):
        """Refresh Square OAuth token."""
        # TODO: Implement token refresh
        pass
