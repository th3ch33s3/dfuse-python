#!/usr/bin/env python
# -*- coding: utf-8 -*-


import datetime
import json
import os
import sqlite3
import tempfile
from typing import Any, Dict, Sequence

import requests
import requests_cache
from decouple import config

from db import persist
from models import TransactionLifecycle


class Dfuse:
    _session = None
    __DEFAULT_BASE_URL: str = ""
    __DEFAULT_TIMEOUT: int = 30
    __TEMPDIR_CACHE: bool = True
    def __UNIXTIMESTAMP(n): return datetime.datetime.fromtimestamp(n)  # TO-USE
    __BLOCK_TIME_URL: str = 'https://mainnet.eos.dfuse.io/v0/block_id/by_time'
    __TRX_URL: str = 'https://mainnet.eos.dfuse.io/v0/transactions'
    __STATE_BASE_URL: str = 'https://mainnet.eos.dfuse.io/v0/state/'
    __API_KEY: str = config('API_KEY')

    def __init__(
        self,
        api_key: str = __API_KEY,
        base_url: str = __DEFAULT_BASE_URL,
        state_base_url: str = __STATE_BASE_URL,
        request_timeout: int = __DEFAULT_TIMEOUT,
        tempdir_cache: bool = __TEMPDIR_CACHE,
        block_by_time_url: str = __BLOCK_TIME_URL,
        trx_url: str = __TRX_URL,
        token: str = '',
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.cache_filename = "dfuse_python.cache"
        self.token = None
        self.block_time_url = block_by_time_url
        self.trx_url = trx_url
        self.abi_url = f'{state_base_url}/abi'
        self.abi_2_bin_url = f'{self.abi_url}/bin_to_json'
        self.key_accounts_url = f'{state_base_url}/key_accounts'
        self.get_table_url = f'{state_base_url}/table'
        self.get_table_row_url = f'{self.get_table}/row'
        self.permission_links_url = f'{state_base_url}/permission_links'
        self.cache_name = (
            os.path.join(tempfile.gettempdir(), self.cache_filename)
            if tempdir_cache
            else self.cache_filename
        )
        self.__get_auth_token()

    @property
    def session(self) -> Any:
        if not self._session:
            self._session = requests_cache.CachedSession(
                cache_name=self.cache_name, backend="sqlite", expire_after=120
            )
            self._session.headers.update({"Content-Type": "application/json"})
            self._session.headers.update({'User-agent': 'dfusepython - python wrapper around \
                                            dfuse.io'})
        return self._session

    def __request_get(self, endpoint, params):
        """
        TO-USE
        """
        response_object = self.session.get(
            endpoint, params=params, timeout=self.request_timeout)

        try:
            response = json.loads(response_object.text)
            if isinstance(response, list) and response_object.status_code == 200:
                response = [
                    dict(item, **{'cached': response_object.from_cache}) for item in response]
            if isinstance(response, dict) and response_object.status_code == 200:
                response['cached'] = response_object.from_cache
        except Exception as e:
            return e
        return response

    def __request_post(self, endpoint, data):
        """
        TO-USE
        """
        response_object = self.session.post(
            endpoint, json=data, timeout=self.request_timeout)
        try:
            response = json.loads(response_object.text)
            if isinstance(response, list) and response_object.status_code == 200:
                response = [
                    dict(item, **{'cached': response_object.from_cache}) for item in response]

            if isinstance(response, dict) and response_object.status_code == 200:
                response['cached'] = response_object.from_cache
        except Exception as ex:
            return ex
        return response

    def save_token_to_db(self, data):
        conn = persist.create_connection()
        if conn is not None:
            # Delete any present entry
            persist.drop_entries(conn)
            persist.create_table(conn)
            persist.insert_token(conn, data)
        else:
            print(f'Failed to connect to db {persist.db_name}')
            return False
        return True

    def is_expired(self, time_, offset_):
        return (((offset_ - time_).total_seconds())//3600) > 22

    def __get_auth_token(self):
        """
        Obtains a short term (24HRS) token

        TODO - cache token for < 24 hrs to avoid rate limits.
        TODO - Check for token in db. Expired? Fetch from API. Rewrite to capture this.

        """
        # Read token from db
        conn = persist.create_connection()
        if conn:
            try:
                tokens = persist.read_token(conn)
                if tokens:
                    created_time = tokens[0][1]
                    leo = datetime.datetime.now()
                    expired = self.is_expired(created_time, leo)
                    if not expired:
                        self.token = tokens[0][0]
                        return self.token

            except sqlite3.OperationalError:
                persist.create_table(conn)

        if not self.token:
            r = requests.post('https://auth.dfuse.io/v1/auth/issue', json={
                'api_key': self.api_key}, headers={'Content-Type': 'application/json'})
            try:
                token = r.json().get('token')
            except Exception:
                raise Exception(
                    f'Failed with status {r.status} and reason {r.json().get("reason")}')
            self.token = token
            if conn:
                data = (token, datetime.datetime.now())
                persist.insert_token(conn, data)
            return self.token
        return self.token

    # REST

    def get_block_at_timestamp(self, time: datetime.datetime = datetime.datetime.now()-datetime.timedelta(1), comparator: str = 'gte'):
        '''
        Fetches the block ID, time and block number for the given timestamp.

        (Beta) GET /v0/block_id/by_time/by_time?time=2019-03-04T10:36:14.5Z&comparator=gte: Get the block ID produced at a given time.

        Defaults to 1 day earlier, if no `time` is supplied, i.e `datetime.datetime.now() - datetime.timedelta(1)`.

        Response:
        ```
        {
            "block": {
                "id": "02bb43ae0d74a228f021f598b552ffb1f8d2de2c29a8ea16a897d643e1d62d62",
                "num": 45826990,
                "time": "2019-03-04T10:36:15Z"
            }
        }
        ```
        '''
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.block_time_url}?time={time}&comparator={comparator}', headers=headers)
        r.raise_for_status()
        return r.json()

    def get_transaction_lifecycle(self, id: str = '02bb43ae0d74a228f021f598b552ffb1f8d2de2c29a8ea16a897d643e1d62d62'):
        '''
        (Beta) GET /v0/transactions/:id: Fetching the transaction lifecycle associated with the provided path parameter :id.

        Fetching the transaction lifecycle associated with the provided path parameter :id.


        This method returns transaction information regardless of the actual lifecycle state be it deferred, executed, failed or cancelled. 

        This means that deferred transactions are handled by this method, via a transaction with a delay_sec argument pushed to the chain or created by a smart contract.

        https://mainnet.eos.dfuse.io/v0/transactions/1d5f57e9392d045ef4d1d19e6976803f06741e11089855b94efcdb42a1a41253

        '''
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }

        r = requests.get(f'{self.trx_url}/{id}', headers=headers)
        r.raise_for_status()

        return r.json()

    def fetch_abi(self, account: str, block_num: int = None, json: bool = True):
        '''
        (Beta) GET /v0/state/abi: Fetch the ABI for a given contract account, at any block height.

        https://mainnet.eos.dfuse.io/v0/state/abi?account=eosio&json=true

        The block_num parameter determines for which block you want the given ABI. This can be anywhere in the chain’s history.

        If the requested block_num is irreversible, you will get an immutable ABI. If the ABI has changed while still in a reversible chain, you will get this new ABI, but it is not guaranteed to be the view that will pass irreversibility. Inspect the returned block_num parameter of the response to understand from which longest chain the returned ABI is from.

        The returned ABI is the one that was active at the block_num requested
        '''
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.abi_url}?account={account}&json={json}&blok_num={block_num}', headers=headers)
        r.raise_for_status()
        return r.json()

    def bin_to_json(self, account: str, table: str, hex_rows: list, block_num: int = None):
        """
        POST /v0/state/abi/bin_to_json 

        Decodes binary rows (in hexadecimal string) for a given table against the ABI 

        of a given contract account, at any block height.

        {
            "account":"eosio.token",
            "table":"accounts",
            "block_num":2500000,
            "hex_rows":["aa2c0b010000000004454f5300000000"]
        }
        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        data = {
            'account': account,
            'table': table,
            'hex_rows': hex_rows,
            'block_num': block_num
        }
        r = requests.post(f'{self.abi_2_bin_url}', json=data, headers=headers)
        r.raise_for_status()
        return r.json()

    def get_key_accounts(self, public_key: str, block_num: int = None):
        """
        GET /v0/state/key_accounts

        Fetches the accounts controlled by the given `public_key`, at any block height, specified by `block_num` (Optional, defaults to `head_block_num`).

        The `block_num` parameter determines for which block height you want a list of accounts associated to the given public key. This can be anywhere in the chain’s history.

        If the requested `block_num` is `irreversible`, you will get an immutable list of accounts. 

        Otherwise, there are chances that the returned value moves as the chain reorganizes.

        NOTE: this will call a drop-in replacement for the /v1/history/get_key_accounts API endpoint from standard `nodeos`

        https://mainnet.eos.dfuse.io/v0/state/key_accounts?public_key=EOS7YNS1swh6QWANkzGgFrjiX8E3u8WK5CK9GMAb6EzKVNZMYhCH3"

        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.key_accounts_url}?public_key={public_key}&block_num={block_num}',
            headers=headers)
        r.raise_for_status()
        return r.json()

    def get_permission_links(self, account: str, block_num: int = None):
        """

        Fetches the accounts controlled by the given public key, at any block height.

        GET /v0/state/permission_links

        The `block_num` parameter determines for which block you want a linked authorizations snapshot. This can be anywhere in the chain’s history.

        If the requested `block_num` is irreversible, you will get an immutable snapshot. If the `block_num` is still in a reversible chain, 

        you will get a full consistent snapshot, but it is not guaranteed to be the view that will pass irreversibility. 

        Inspect the returned `up_to_block_id` parameter to understand from which longest chain the returned value is a snapshot of. 

        https://mainnet.eos.dfuse.io/v0/state/permission_links?account=eoscanadacom&block_num=10000000

        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.permission_links_url}?account={account}&block_num={block_num}', headers=headers)

        r.raise_for_status()
        return r.json()

    def get_table(self, account: str, scope: str, table: str, block_num: int = None, json: bool = True, key_type: str = 'name', with_block_num: bool = false, with_abi: bool = false):
        """
        GET /v0/state/table

        Fetches the state of any table, at any block height.

        Valid key_type arguments could be:

            `name` (default) for EOS name-encoded base32 representation of the row key

            `hex` for hexadecimal encoding, ex: abcdef1234567890

            `hex_be` for big endian hexadecimal encoding, ex: 9078563412efcdab

            `uint64` for string encoded uint64. Beware: uint64 can be very large numbers and some programming languages need special care to 

                    decode them without truncating their value. This is why they are returned as strings

        The `block_num` parameter determines for which block you want a table snapshot. This can be anywhere in the chain’s history.

        If the requested `block_num` is irreversible, you will get an immutable snapshot. 

        If the `block_num` is still in a reversible chain, you will get a full consistent snapshot, but it is not guaranteed to pass irreversibility. 

        Inspect the returned up_to_block_id parameter to understand from which longest chain the returned value is a snapshot of.

        https://mainnet.eos.dfuse.io/v0/state/table?account=eosio.token&scope=b1&table=accounts&block_num=25000000&json=true
        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.get_table_url}?account={account}&scope={scope}&table={table}&block_num={block_num}&json={json}&key_type={key_type}&with_block_num={with_block_num}&with_abi={with_abi}')
        r.raise_for_status()
        return r.json()

    def get_table_rows(self, account: str, scope: str, table: str, primary_key: str, block_num: int,  key_type: str = 'symbol_code', json: bool = True):
        """
        GET /v0/state/table/row

        Fetches a single row from the state of any table, at any block height.

        The block_num parameter determines for which block you want a table row snapshot. This can be anywhere in the chain’s history.

        If the requested block_num is irreversible, you will get an immutable snapshot. 

        If the block_num is still in a reversible chain, you will get a full consistent snapshot, but it is not guaranteed to pass irreversibility. 

        Inspect the returned up_to_block_id parameter to understand from which longest chain the returned value is a snapshot of.

        The dfuse API tracks ABI changes and will the row with the ABI in effect at the block_num requested.

        Row is decoded only if json: true is passed. Otherwise, hexadecimal of its binary data is returned instead.

        If you requested a json-decoded form but it was impossible to decode a row (ex: the ABI was not well formed at that block_num), 

        the hex representation would be returned along with an error field containing the decoding error.

        https://mainnet.eos.dfuse.io/v0/state/table/row?account=eosio.token&scope=b1&table=accounts&primary_key=EOS&key_type=symbol_code&block_num=25000000&json=true

        `key_type`s:

                `name` (default) for EOS name-encoded base32 representation of the row key.

                `symbol` for EOS asset’s symbol representation of the row key, a symbol is always composed of a precision and symbol code in the form of 4,EOS.

                `symbol_code` for EOS asset’s symbol code representation of the row key, a symbol code is always composed of solely of 1 to 7 upper case characters like EOS.

                `hex` for hexadecimal encoding, ex: abcdef1234567890.

                `hex_be` for big endian hexadecimal encoding, ex: 9078563412efcdab.

                `uint64` for string encoded uint64. Beware: uint64 can be very large numbers and some programming languages need special care to decode them without truncating their value. This is why they are returned as strings.

        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(
            f'{self.get_table_row_url}?account={account}&scope={scope}&table={table}&primary_key={primary_key}&key_type={key_type}&block_num={block_num}&json={json}', headers=headers)
        r.raise_for_status()
        return r.json()

    def get_table_accounts(self):
        """
        GET /v0/state/table/accounts: Fetching snapshots of any table on the blockchain, at any block height, for a list of accounts (contracts).
        """
        headers: dict = {
            'Authorization': f'Bearer {self.token}'
        }
        r = requests.get(f'')

    """

    (Beta) GET /v0/state/table: Fetching snapshots of any table on the blockchain, at any block height.

    (Beta) 

    (Beta) GET /v0/state/table/scopes: Fetching snapshots of any table on the blockchain, at any block height, for a list of scopes for a given account (contract).

    (Beta) GET /v0/search/transactions: Structure Query Engine (SQE), for searching the whole blockchain history and get fast and precise results.

    (Beta) POST /v1/chain/push_transaction: Drop-in replacement for submitting a transaction to the network, but can optionally block the request until the transaction is either in a block or in an irreversible block.

    Other /v1/chain/...: Reverse-proxy of all standard chain requests to a well-connected node.
    """

    # WEBSOCKETS
    """
    type	string	required	The type of the message. See request types below.
    data	object	required	A free-form object, specific to the type of request. See request types below.
    req_id	string	optional	An ID to associate responses back with the request
    start_block	number (integer)	optional	Block at which you want to start processing. It can be an absolute block number, or a negative value, meaning how many blocks from the current head block on the chain. Ex: -2500 means 2500 blocks in the past, relative to the head block. 0 means the beginning of the chain. See Never missing a beat
    irreversible_only	boolean	optional, defaults to false	Limits output to events that happened in irreversible blocks. Only supported on get_action_traces
    fetch	boolean	optional, defaults to false	Whether to fetch an initial snapshot of the requested entity.
    listen	boolean	optional, defaults to false	Whether to start listening on changes to the requested entity.
    with_progress	number (integer)	optional	Frequency of the progress of blocks processi
    """

    # GRAPHQL via grpc
