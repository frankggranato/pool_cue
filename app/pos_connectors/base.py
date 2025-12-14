"""
Base POS Connector class.
All POS integrations (Toast, Square, etc.) should inherit from this.
"""

class BasePOSConnector:
    """Base class for POS system connectors."""
    
    def __init__(self, credentials):
        """
        Initialize connector with credentials.
        
        Args:
            credentials: dict with access_token, refresh_token, etc.
        """
        self.credentials = credentials
        self.access_token = credentials.get('access_token')
        self.refresh_token = credentials.get('refresh_token')
    
    def fetch_checks(self, bar, start_date, end_date):
        """
        Fetch check/order data from the POS system.
        
        Args:
            bar: dict with bar info including pos_location_id
            start_date: datetime or string
            end_date: datetime or string
            
        Returns:
            List of check dictionaries with standardized format:
            [{
                'check_id': str,
                'opened_at': datetime,
                'closed_at': datetime,
                'total': float,
                'items': [{name, quantity, price}],
                'raw_data': dict  # original POS response
            }]
        """
        raise NotImplementedError("Subclasses must implement fetch_checks")
    
    def test_connection(self):
        """Test if credentials are valid."""
        raise NotImplementedError("Subclasses must implement test_connection")
    
    def refresh_access_token(self):
        """Refresh the access token if expired."""
        raise NotImplementedError("Subclasses must implement refresh_access_token")
