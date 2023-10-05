import json
from http import HTTPStatus

import boto3
from botocore.stub import Stubber

from product.crud.handlers.handle_create_product import lambda_handler
from product.crud.integration.dynamo_dal_handler import DynamoDalHandler
from product.crud.integration.schemas.db import Product
from tests.crud_utils import generate_api_gw_event, generate_create_product_request_body, generate_product_id
from tests.utils import generate_context


def test_handler_200_ok(table_name: str):
    # GIVEN a product creation request
    body = generate_create_product_request_body()
    product_id = generate_product_id()

    # WHEN the lambda handler processes the request
    response = lambda_handler(
        event=generate_api_gw_event(product_id=product_id, body=body.model_dump(), path_params={'product': product_id}),
        context=generate_context(),
    )

    # THEN the response should indicate successful creation (HTTP 200 OK) and contain correct product data
    assert response['statusCode'] == HTTPStatus.OK
    body_dict = json.loads(response['body'])
    assert body_dict['id'] == product_id

    # AND the DynamoDB table should contain the new product with correct data
    dynamodb_table = boto3.resource('dynamodb').Table(table_name)
    response = dynamodb_table.get_item(Key={'id': product_id})
    assert 'Item' in response
    assert response['Item']['name'] == body.name
    assert response['Item']['price'] == body.price
    assert response['Item']['id'] == product_id


def test_handler_bad_request_product_already_exists(add_product_entry_to_db: Product):
    # GIVEN a product that already exists in the database
    product_id = add_product_entry_to_db.id

    # WHEN attempting to create a product with the same ID
    response = lambda_handler(
        event=generate_api_gw_event(product_id=product_id, body=add_product_entry_to_db.model_dump(), path_params={'product': product_id}),
        context=generate_context(),
    )

    # THEN the response should indicate a bad request due to existing product (HTTP 400 Bad Request)
    # AND contain an appropriate error message
    assert response['statusCode'] == HTTPStatus.BAD_REQUEST
    body_dict = json.loads(response['body'])
    assert body_dict['error'] == 'product already exists'


def test_internal_server_error(table_name: str):
    # GIVEN a DynamoDB exception scenario
    db_handler: DynamoDalHandler = DynamoDalHandler(table_name)
    table = db_handler._get_db_handler(table_name)

    with Stubber(table.meta.client) as stubber:
        stubber.add_client_error(method='put_item', service_error_code='ValidationException')
        body = generate_create_product_request_body()
        product_id = generate_product_id()

        # WHEN attempting to create a product while the DynamoDB exception is triggered
        response = lambda_handler(
            event=generate_api_gw_event(product_id=product_id, body=body.model_dump(), path_params={'product': product_id}),
            context=generate_context(),
        )

    # THEN the response should indicate an internal server error (HTTP 500 Internal Server Error)
    # AND contain an appropriate error message
    assert response['statusCode'] == HTTPStatus.INTERNAL_SERVER_ERROR
    body_dict = json.loads(response['body'])
    assert body_dict['error'] == 'internal server error'


def test_handler_bad_request_invalid_body_input():
    # GIVEN an invalid product creation request with insufficient body input
    product_id = generate_product_id()

    # WHEN the lambda handler processes the request
    response = lambda_handler(
        event=generate_api_gw_event(product_id=product_id, body={'price': 5}, path_params={'product': product_id}),
        context=generate_context(),
    )

    # THEN the response should indicate bad request due to invalid input (HTTP 400 Bad Request)
    # AND contain an appropriate error message
    assert response['statusCode'] == HTTPStatus.BAD_REQUEST
    body_dict = json.loads(response['body'])
    assert body_dict['error'] == 'invalid input'


def test_handler_bad_request_invalid_path_params():
    # GIVEN an invalid product creation request with incorrect path parameters
    body = generate_create_product_request_body()
    product_id = generate_product_id()

    # WHEN the lambda handler processes the request
    response = lambda_handler(
        event=generate_api_gw_event(product_id=product_id, body=body.model_dump(), path_params={'dummy': product_id}, path='dummy'),
        context=generate_context(),
    )

    # THEN the response should indicate a not found error (HTTP 404 Not Found)
    assert response['statusCode'] == HTTPStatus.NOT_FOUND
