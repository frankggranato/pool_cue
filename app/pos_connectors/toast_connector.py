"""
Toast POS Connector stub.
Will integrate with Toast API when credentials are available.
"""

from .base import BasePOSConnector


class ToastConnector(BasePOSConnector):
    """Connector for Toast POS system."""
    
    API_BASE_URL = "https://api.toasttab.com"
    
    def __init__(self, credentials):
        super().__init__(credentials)
        self.location_guid = credentials.get('location_id')
    
    def fetch_checks(self, bar, start_date, end_date):
        """
        Fetch checks from Toast API.
        
        Toast API endpoint: GET /orders/v2/orders
        Requires: location GUID, date range
        
        For now, returns empty list (stub implementation).
        """
        # TODO: Implement actual Toast API call
        # Example:
        # headers = {'Authorization': f'Bearer {self.access_token}'}
        # params = {
        #     'startDate': start_date.isoformat(),
        #     'endDate': end_date.isoformat(),
        # }
        # response = requests.get(
        #     f'{self.API_BASE_URL}/orders/v2/orders',
        #     headers=headers,
        #     params=params
        # )
        return []
    
    def test_connection(self):
        """Test Toast API credentials."""
        # TODO: Make a simple API call to verify credentials
        return {'success': False, 'error': 'Not implemented'}
    
    def refresh_access_token(self):
        """Refresh Toast OAuth token."""
        # TODO: Implement token refresh
        pass
