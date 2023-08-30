from aws_cdk import CfnOutput, Duration, aws_apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk.aws_lambda_python_alpha import PythonLayerVersion
from aws_cdk.aws_logs import RetentionDays
from constructs import Construct

import infrastructure.product.constants as constants
from infrastructure.product.crud_api_db_construct import ApiDbConstruct


class CrudApiConstruct(Construct):

    def __init__(self, scope: Construct, id_: str, lambda_layer: PythonLayerVersion) -> None:
        super().__init__(scope, id_)
        self.api_db = ApiDbConstruct(self, f'{id_}db')
        self.lambda_role = self._build_lambda_role(self.api_db.db, self.api_db.idempotency_db)
        self.common_layer = lambda_layer
        self.rest_api = self._build_api_gw()
        api_resource: aws_apigateway.Resource = self.rest_api.root.add_resource('api').add_resource(constants.GW_RESOURCE)
        self._add_put_product_lambda_integration(api_resource, self.lambda_role, self.api_db.db, self.api_db.idempotency_db)

    def _build_api_gw(self) -> aws_apigateway.RestApi:
        rest_api: aws_apigateway.RestApi = aws_apigateway.RestApi(
            self,
            constants.REST_API_NAME,
            rest_api_name='Product CRUD Rest API',
            description='This service handles /api/product requests',
            deploy_options=aws_apigateway.StageOptions(throttling_rate_limit=2, throttling_burst_limit=10),
            cloud_watch_role=False,
        )

        CfnOutput(self, id=constants.APIGATEWAY, value=rest_api.url).override_logical_id(constants.APIGATEWAY)
        return rest_api

    def _build_lambda_role(self, db: dynamodb.Table, idempotency_table: dynamodb.Table) -> iam.Role:
        return iam.Role(
            self,
            constants.SERVICE_ROLE_ARN,
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            inline_policies={
                'dynamodb_db':
                    iam.PolicyDocument(
                        statements=[iam.PolicyStatement(
                            actions=['dynamodb:PutItem'],
                            resources=[db.table_arn],
                            effect=iam.Effect.ALLOW,
                        )]),
                'idempotency_table':
                    iam.PolicyDocument(statements=[
                        iam.PolicyStatement(
                            actions=['dynamodb:PutItem', 'dynamodb:GetItem', 'dynamodb:UpdateItem', 'dynamodb:DeleteItem'],
                            resources=[idempotency_table.table_arn],
                            effect=iam.Effect.ALLOW,
                        )
                    ]),
            },
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name=(f'service-role/{constants.LAMBDA_BASIC_EXECUTION_ROLE}'))
            ],
        )

    def _add_put_product_lambda_integration(
        self,
        api_resource: aws_apigateway.Resource,
        role: iam.Role,
        db: dynamodb.Table,
        idempotency_table: dynamodb.Table,
    ):
        put_resource = api_resource.add_resource('{product}')
        lambda_function = _lambda.Function(
            self,
            constants.CREATE_LAMBDA,
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset(constants.BUILD_FOLDER),
            handler='product.crud.handlers.create_product.create_product',
            environment={
                constants.POWERTOOLS_SERVICE_NAME: constants.SERVICE_NAME,  # for logger, tracer and metrics
                constants.POWER_TOOLS_LOG_LEVEL: 'DEBUG',  # for logger
                'TABLE_NAME': db.table_name,
                'IDEMPOTENCY_TABLE_NAME': idempotency_table.table_name,
            },
            tracing=_lambda.Tracing.ACTIVE,
            retry_attempts=0,
            timeout=Duration.seconds(constants.API_HANDLER_LAMBDA_TIMEOUT),
            memory_size=constants.API_HANDLER_LAMBDA_MEMORY_SIZE,
            layers=[self.common_layer],
            role=role,
            log_retention=RetentionDays.ONE_DAY,
        )

        # PUT /api/product/{product}/
        put_resource.add_method(http_method='PUT', integration=aws_apigateway.LambdaIntegration(handler=lambda_function))