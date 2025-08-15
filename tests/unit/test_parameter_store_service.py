"""
Parameter Store統合サービスのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError

from src.services.parameter_store_service import (
    ParameterStoreService,
    ParameterStoreConfig,
    ParameterCacheEntry
)


class TestParameterCacheEntry:
    """ParameterCacheEntryクラスのテスト"""
    
    def test_cache_entry_not_expired(self):
        """期限内のキャッシュエントリ"""
        entry = ParameterCacheEntry(
            value="test_value",
            last_updated=datetime.now(),
            ttl_seconds=300
        )
        assert not entry.is_expired
    
    def test_cache_entry_expired(self):
        """期限切れのキャッシュエントリ"""
        entry = ParameterCacheEntry(
            value="test_value",
            last_updated=datetime.now() - timedelta(seconds=400),
            ttl_seconds=300
        )
        assert entry.is_expired


class TestParameterStoreService:
    """ParameterStoreServiceクラスのテスト"""
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_initialization_success(self, mock_boto3):
        """正常な初期化"""
        mock_session = Mock()
        mock_credentials = Mock()
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        
        mock_client = Mock()
        mock_client.describe_parameters.return_value = {}
        mock_boto3.client.return_value = mock_client
        
        service = ParameterStoreService()
        
        assert service.is_available
        mock_boto3.client.assert_called_with('ssm', region_name='ap-northeast-1')
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_initialization_no_credentials(self, mock_boto3):
        """認証情報なしの初期化"""
        mock_session = Mock()
        mock_session.get_credentials.return_value = None
        mock_boto3.Session.return_value = mock_session
        
        with pytest.raises(NoCredentialsError):
            ParameterStoreService()
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', False)
    def test_initialization_no_boto3(self):
        """boto3なしの初期化"""
        service = ParameterStoreService()
        assert not service.is_available
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_get_parameter_success(self, mock_boto3):
        """パラメータ取得成功"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.get_parameter.return_value = {
            'Parameter': {'Value': 'test_value'}
        }
        
        service = ParameterStoreService()
        result = service.get_parameter('/test/parameter')
        
        assert result == 'test_value'
        mock_client.get_parameter.assert_called_with(
            Name='/test/parameter',
            WithDecryption=False
        )
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_get_parameter_not_found(self, mock_boto3):
        """パラメータが見つからない場合"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.get_parameter.side_effect = ClientError(
            {'Error': {'Code': 'ParameterNotFound'}},
            'GetParameter'
        )
        
        service = ParameterStoreService()
        
        with pytest.raises(ValueError, match="パラメータが見つかりません"):
            service.get_parameter('/test/parameter')
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True) 
    @patch('src.services.parameter_store_service.boto3')
    def test_get_parameter_with_cache(self, mock_boto3):
        """キャッシュ機能のテスト"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.get_parameter.return_value = {
            'Parameter': {'Value': 'cached_value'}
        }
        
        service = ParameterStoreService()
        
        # 初回取得
        result1 = service.get_parameter('/test/parameter', use_cache=True)
        assert result1 == 'cached_value'
        
        # 2回目はキャッシュから取得（APIコールなし）
        result2 = service.get_parameter('/test/parameter', use_cache=True)
        assert result2 == 'cached_value'
        
        # APIは1回だけ呼ばれる
        assert mock_client.get_parameter.call_count == 1
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_get_parameters_by_path(self, mock_boto3):
        """パス指定でのパラメータ一括取得"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.get_parameters_by_path.return_value = {
            'Parameters': [
                {'Name': '/app/db/host', 'Value': 'localhost'},
                {'Name': '/app/db/port', 'Value': '5432'}
            ]
        }
        
        service = ParameterStoreService()
        result = service.get_parameters_by_path('/app/')
        
        assert result == {
            '/app/db/host': 'localhost',
            '/app/db/port': '5432'
        }
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_put_parameter_success(self, mock_boto3):
        """パラメータ保存成功"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.put_parameter.return_value = {}
        
        service = ParameterStoreService()
        result = service.put_parameter(
            '/test/param',
            'test_value',
            'String',
            'Test parameter'
        )
        
        assert result is True
        mock_client.put_parameter.assert_called_with(
            Name='/test/param',
            Value='test_value',
            Type='String',
            Description='Test parameter',
            Overwrite=True
        )
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_validate_connection_success(self, mock_boto3):
        """接続検証成功"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.describe_parameters.return_value = {}
        
        service = ParameterStoreService()
        assert service.validate_connection() is True
    
    @patch('src.services.parameter_store_service.AWS_AVAILABLE', True)
    @patch('src.services.parameter_store_service.boto3')
    def test_validate_connection_failure(self, mock_boto3):
        """接続検証失敗"""
        mock_client = self._setup_mock_client(mock_boto3)
        mock_client.describe_parameters.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied'}},
            'DescribeParameters'
        )
        
        service = ParameterStoreService()
        assert service.validate_connection() is False
    
    def test_cache_management(self):
        """キャッシュ管理機能"""
        service = ParameterStoreService()
        
        # キャッシュに手動でエントリを追加
        service._save_to_cache('test_param', 'test_value', 300, False)
        
        # キャッシュ情報を取得
        cache_info = service.get_cache_info()
        assert cache_info['total_entries'] == 1
        assert len(cache_info['entries']) == 1
        
        # キャッシュクリア
        service.clear_cache()
        cache_info_after_clear = service.get_cache_info()
        assert cache_info_after_clear['total_entries'] == 0
    
    def _setup_mock_client(self, mock_boto3):
        """モッククライアントのセットアップ"""
        mock_session = Mock()
        mock_credentials = Mock()
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        
        mock_client = Mock()
        mock_client.describe_parameters.return_value = {}
        mock_boto3.client.return_value = mock_client
        
        return mock_client


class TestParameterStoreConfig:
    """ParameterStoreConfigクラスのテスト"""
    
    def test_get_parameter_path(self):
        """パラメータパスの取得"""
        path = ParameterStoreConfig.get_parameter_path('google_sheets_id')
        assert path == '/stock-analysis/google-sheets-id'
        
        # 未定義のキー
        custom_path = ParameterStoreConfig.get_parameter_path('custom_param')
        assert custom_path == '/stock-analysis/custom_param'
    
    def test_is_secure_parameter(self):
        """セキュアパラメータの判定"""
        assert ParameterStoreConfig.is_secure_parameter('gemini_api_key') is True
        assert ParameterStoreConfig.is_secure_parameter('slack_webhook') is True
        assert ParameterStoreConfig.is_secure_parameter('google_sheets_id') is False
        assert ParameterStoreConfig.is_secure_parameter('log_level') is False
    
    def test_get_all_parameter_paths(self):
        """全パラメータパスの取得"""
        paths = ParameterStoreConfig.get_all_parameter_paths()
        assert '/stock-analysis/google-sheets-id' in paths
        assert '/stock-analysis/gemini-api-key' in paths
        assert '/stock-analysis/slack-webhook' in paths
    
    def test_validate_parameter_structure(self):
        """パラメータ構造の検証"""
        # 有効なパラメータ
        valid_params = {
            'google_sheets_id': '1234567890abcdef',
            'gemini_api_key': 'AIzaSyTest123456',
            'slack_webhook': 'https://hooks.slack.com/services/test'
        }
        errors = ParameterStoreConfig.validate_parameter_structure(valid_params)
        assert len(errors) == 0
        
        # 無効なパラメータ（必須パラメータ不足）
        invalid_params = {
            'google_sheets_id': '1234567890abcdef'
            # gemini_api_key, slack_webhook が不足
        }
        errors = ParameterStoreConfig.validate_parameter_structure(invalid_params)
        assert len(errors) > 0
        assert any('必須パラメータが不足' in error for error in errors)
        
        # 空の値
        empty_params = {
            'google_sheets_id': '',
            'gemini_api_key': 'valid_key',
            'slack_webhook': 'valid_url'
        }
        errors = ParameterStoreConfig.validate_parameter_structure(empty_params)
        assert len(errors) > 0
        assert any('google_sheets_id\' が空です' in error for error in errors)