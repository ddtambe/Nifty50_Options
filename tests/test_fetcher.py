"""Tests for 5paisa option chain fetcher."""
import os
import pytest
from unittest.mock import patch, MagicMock

from nifty_oc.fetcher import fetch_option_chain, FetchError, _get_credentials, _generate_totp


# Mock credentials for all tests
MOCK_CREDS = {
    "FIVEPAISA_APP_NAME": "test_app",
    "FIVEPAISA_APP_SOURCE": "test_source",
    "FIVEPAISA_USER_ID": "test_user",
    "FIVEPAISA_PASSWORD": "test_pass",
    "FIVEPAISA_USER_KEY": "test_key",
    "FIVEPAISA_ENCRYPTION_KEY": "test_enc",
    "FIVEPAISA_CLIENT_CODE": "test_client",
    "FIVEPAISA_TOTP_SECRET": "JBSWY3DPEHPK3PXP",  # Valid base32 test secret
    "FIVEPAISA_PIN": "1234",
}

# Sample expiry timestamp (milliseconds) - Aug 7, 2026
SAMPLE_EXPIRY_TS = 1786041000000


class TestGetCredentials:
    def test_returns_credentials_when_all_present(self):
        with patch.dict(os.environ, MOCK_CREDS):
            cred, login = _get_credentials()
            assert cred["APP_NAME"] == "test_app"
            assert cred["USER_ID"] == "test_user"
            assert login["CLIENT_CODE"] == "test_client"
            assert login["PIN"] == "1234"

    def test_raises_when_credential_missing(self):
        partial = {k: v for k, v in MOCK_CREDS.items() if k != "FIVEPAISA_PASSWORD"}
        with patch.dict(os.environ, partial, clear=True):
            with pytest.raises(FetchError) as exc_info:
                _get_credentials()
            assert "FIVEPAISA_PASSWORD" in str(exc_info.value)

    def test_raises_when_login_credential_missing(self):
        partial = {k: v for k, v in MOCK_CREDS.items() if k != "FIVEPAISA_TOTP_SECRET"}
        with patch.dict(os.environ, partial, clear=True):
            with pytest.raises(FetchError) as exc_info:
                _get_credentials()
            assert "FIVEPAISA_TOTP_SECRET" in str(exc_info.value)


class TestGenerateTotp:
    def test_generates_6_digit_code(self):
        # Use a known test secret
        code = _generate_totp("JBSWY3DPEHPK3PXP")
        assert len(code) == 6
        assert code.isdigit()

    def test_handles_lowercase_secret(self):
        code = _generate_totp("jbswy3dpehpk3pxp")
        assert len(code) == 6


class TestFetchOptionChain:
    def test_fetch_succeeds_with_valid_data(self):
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = {
            "Options": [
                {
                    "StrikeRate": 24800,
                    "CPType": "CE",
                    "OpenInterest": 1000,
                    "ChangeInOI": 100,
                    "LastRate": 150.5,
                    "IV": 15.5,
                    "Volume": 5000,
                    "UnderlyingValue": 24812.35,
                },
                {
                    "StrikeRate": 24800,
                    "CPType": "PE",
                    "OpenInterest": 800,
                    "ChangeInOI": -50,
                    "LastRate": 120.0,
                    "IV": 14.2,
                    "Volume": 4000,
                },
            ]
        }

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                result = fetch_option_chain()

        assert "records" in result
        assert result["records"]["underlyingValue"] == 24812.35
        assert len(result["records"]["data"]) > 0

    def test_fetch_raises_when_spot_unresolvable(self):
        """Options present but no spot anywhere, and market feed also empty:
        must raise, NOT silently return the 24000.0 placeholder."""
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = {
            "Options": [
                {"StrikeRate": 24800, "CPType": "CE", "OpenInterest": 1000},
            ]
        }
        mock_client.fetch_market_feed_scrip.return_value = []

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                with pytest.raises(FetchError) as exc_info:
                    fetch_option_chain()
        assert "spot" in str(exc_info.value).lower()

    def test_fetch_uses_market_feed_spot_when_chain_lacks_it(self):
        """No UnderlyingValue in chain, but market feed provides the spot."""
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = {
            "Options": [
                {"StrikeRate": 24800, "CPType": "CE", "OpenInterest": 1000},
            ]
        }
        mock_client.fetch_market_feed_scrip.return_value = [{"LastRate": 24777.7}]

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                result = fetch_option_chain()
        assert result["records"]["underlyingValue"] == 24777.7

    def test_fetch_raises_on_empty_data(self):
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = {"Options": []}

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                with pytest.raises(FetchError) as exc_info:
                    fetch_option_chain()
                assert "No option chain data" in str(exc_info.value)

    def test_fetch_raises_on_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(FetchError) as exc_info:
                fetch_option_chain()
            assert "Missing credentials" in str(exc_info.value)

    def test_fetch_handles_list_response_format(self):
        """5paisa may return options as a list instead of dict with Options key."""
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = [
            {
                "Strike": 24900,
                "OptionType": "CALL",
                "OI": 500,
                "NetChangeInOI": 25,
                "LTP": 100.0,
                "ImpliedVolatility": 16.0,
                "TradedQty": 3000,
                "SpotPrice": 24850.0,
            }
        ]

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                result = fetch_option_chain()

        assert result["records"]["underlyingValue"] == 24850.0
        assert len(result["records"]["data"]) > 0

    def test_fetch_handles_expiry_dict_format(self):
        """5paisa may return expiry as dict with Expiry key."""
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = {"Expiry": [SAMPLE_EXPIRY_TS]}
        mock_client.get_option_chain.return_value = {
            "Options": [
                {
                    "StrikeRate": 24800,
                    "CPType": "CE",
                    "OpenInterest": 1000,
                    "UnderlyingValue": 24812.35,
                },
            ]
        }

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                result = fetch_option_chain()

        assert result["records"]["underlyingValue"] == 24812.35

    def test_fetch_handles_api_exception(self):
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.side_effect = Exception("API timeout")

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                with pytest.raises(FetchError) as exc_info:
                    fetch_option_chain()
                assert "No option chain data" in str(exc_info.value)

    def test_nse_format_compatibility(self):
        """Verify output matches expected NSE format for pipeline compatibility."""
        mock_client = MagicMock()
        mock_client.get_expiry.return_value = [SAMPLE_EXPIRY_TS]
        mock_client.get_option_chain.return_value = {
            "Options": [
                {
                    "StrikeRate": 24800,
                    "CPType": "CE",
                    "OpenInterest": 1000,
                    "ChangeInOI": 100,
                    "LastRate": 150.5,
                    "IV": 15.5,
                    "Volume": 5000,
                    "UnderlyingValue": 24812.35,
                },
            ]
        }

        with patch.dict(os.environ, MOCK_CREDS):
            with patch("nifty_oc.fetcher.FivePaisaClient", return_value=mock_client):
                result = fetch_option_chain()

        # Verify NSE-like structure
        records = result["records"]
        assert "underlyingValue" in records
        assert "expiryDates" in records
        assert "data" in records
        assert isinstance(records["expiryDates"], list)

        # Verify data entry structure
        entry = records["data"][0]
        assert "strikePrice" in entry
        assert "expiryDate" in entry
        assert "CE" in entry or "PE" in entry

        # Verify CE/PE leg structure
        if entry.get("CE"):
            ce = entry["CE"]
            assert "openInterest" in ce
            assert "changeinOpenInterest" in ce
            assert "lastPrice" in ce
            assert "impliedVolatility" in ce
            assert "totalTradedVolume" in ce
