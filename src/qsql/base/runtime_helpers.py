# [CUSTOM] 运行期交互与训练计划逻辑从 base.py 外拆，降低主基类文件体积。
from __future__ import annotations

import importlib
import importlib.util
import traceback
from typing import Any, List, Union

import pandas as pd

from ..exceptions import ImproperlyConfigured, ValidationError
from ..types import TrainingPlan, TrainingPlanItem


def _get_ipython_display_module():
    if importlib.util.find_spec("IPython.display") is None:
        return None
    return importlib.import_module("IPython.display")


def ask_impl(
    vn: Any,
    question: Union[str, None] = None,
    print_results: bool = True,
    auto_train: bool = True,
    visualize: bool = True,
    allow_llm_to_see_data: bool = False,
):
    if question is None:
        question = input("Enter a question: ")

    try:
        sql = vn.generate_sql(
            question=question, allow_llm_to_see_data=allow_llm_to_see_data
        )
    except Exception as e:
        print(e)
        return None, None, None

    display_module = _get_ipython_display_module()
    if print_results:
        if display_module is not None:
            display_module.display(display_module.Code(sql))
        else:
            print(sql)

    if vn.run_sql_is_set is False:
        print("If you want to run the SQL query, connect to a database first.")
        if print_results:
            return None
        return sql, None, None

    try:
        df = vn.run_sql(sql)

        if print_results:
            if display_module is not None:
                display_module.display(df)
            else:
                print(df)

        if len(df) > 0 and auto_train:
            vn.add_question_sql(question=question, sql=sql)

        if visualize:
            try:
                plotly_code = vn.generate_plotly_code(
                    question=question,
                    sql=sql,
                    df_metadata=f"Running df.dtypes gives:\n {df.dtypes}",
                )
                fig = vn.get_plotly_figure(plotly_code=plotly_code, df=df)
                if print_results:
                    if display_module is not None:
                        img_bytes = fig.to_image(format="png", scale=2)
                        display_module.display(display_module.Image(img_bytes))
                    else:
                        fig.show()
            except Exception as e:
                traceback.print_stack()
                traceback.print_exc()
                print("Couldn't run plotly code: ", e)
                if print_results:
                    return None
                return sql, df, None
        else:
            return sql, df, None

    except Exception as e:
        print("Couldn't run sql: ", e)
        if print_results:
            return None
        return sql, None, None
    return sql, df, fig


def train_impl(
    vn: Any,
    question: str = None,
    sql: str = None,
    ddl: str = None,
    documentation: str = None,
    plan: TrainingPlan = None,
    qsql_log_fn=None,
    qsql_hash_fn=None,
    qsql_len_fn=None,
):
    if qsql_log_fn is not None and qsql_hash_fn is not None and qsql_len_fn is not None:
        qsql_log_fn(
            "info",
            "[QSQL] base训练入口 "
            f"has_question={question is not None} question_hash={qsql_hash_fn(question)} "
            f"question_len={qsql_len_fn(question)} has_sql={sql is not None} "
            f"sql_hash={qsql_hash_fn(sql)} sql_len={qsql_len_fn(sql)} "
            f"has_ddl={ddl is not None} has_documentation={documentation is not None} "
            f"has_plan={plan is not None}",
        )

    if question and not sql:
        raise ValidationError("Please also provide a SQL query")

    if documentation:
        print("Adding documentation....")
        return vn.add_documentation(documentation)

    if sql:
        if question is None:
            question = vn.generate_question(sql)
            if (
                qsql_log_fn is not None
                and qsql_hash_fn is not None
                and qsql_len_fn is not None
            ):
                qsql_log_fn(
                    "info",
                    "[QSQL] base训练自动生成问题 "
                    f"question_hash={qsql_hash_fn(question)} question_len={qsql_len_fn(question)} "
                    f"sql_hash={qsql_hash_fn(sql)}",
                )
            print("Question generated with sql:", question, "\nAdding SQL...")
        return vn.add_question_sql(question=question, sql=sql)

    if ddl:
        print("Adding ddl:", ddl)
        return vn.add_ddl(ddl)

    if plan:
        for item in plan._plan:
            if item.item_type == TrainingPlanItem.ITEM_TYPE_DDL:
                vn.add_ddl(item.item_value)
            elif item.item_type == TrainingPlanItem.ITEM_TYPE_IS:
                vn.add_documentation(item.item_value)
            elif item.item_type == TrainingPlanItem.ITEM_TYPE_SQL:
                vn.add_question_sql(question=item.item_name, sql=item.item_value)

    return None


def get_databases_impl(vn: Any) -> List[str]:
    try:
        print("Trying INFORMATION_SCHEMA.DATABASES")
        df_databases = vn.run_sql("SELECT * FROM INFORMATION_SCHEMA.DATABASES")
    except Exception as e:
        print(e)
        try:
            print("Trying SHOW DATABASES")
            df_databases = vn.run_sql("SHOW DATABASES")
        except Exception as e:
            print(e)
            return []

    return df_databases["DATABASE_NAME"].unique().tolist()


def get_information_schema_tables_impl(vn: Any, database: str) -> pd.DataFrame:
    return vn.run_sql(f"SELECT * FROM {database}.INFORMATION_SCHEMA.TABLES")


def get_training_plan_generic_impl(df) -> TrainingPlan:
    database_column = df.columns[
        df.columns.str.lower().str.contains("database")
        | df.columns.str.lower().str.contains("table_catalog")
    ].to_list()[0]
    schema_column = df.columns[
        df.columns.str.lower().str.contains("table_schema")
    ].to_list()[0]
    table_column = df.columns[
        df.columns.str.lower().str.contains("table_name")
    ].to_list()[0]
    columns = [database_column, schema_column, table_column]
    candidates = ["column_name", "data_type", "comment"]
    matches = df.columns.str.lower().str.contains("|".join(candidates), regex=True)
    columns += df.columns[matches].to_list()

    plan = TrainingPlan([])

    for database in df[database_column].unique().tolist():
        for schema in (
            df.query(f'{database_column} == "{database}"')[schema_column]
            .unique()
            .tolist()
        ):
            for table in (
                df.query(
                    f'{database_column} == "{database}" and {schema_column} == "{schema}"'
                )[table_column]
                .unique()
                .tolist()
            ):
                df_columns_filtered_to_table = df.query(
                    f'{database_column} == "{database}" and {schema_column} == "{schema}" and {table_column} == "{table}"'
                )
                doc = (
                    f"The following columns are in the {table} table in the {database} database:\n\n"
                )
                doc += df_columns_filtered_to_table[columns].to_markdown()

                plan._plan.append(
                    TrainingPlanItem(
                        item_type=TrainingPlanItem.ITEM_TYPE_IS,
                        item_group=f"{database}.{schema}",
                        item_name=table,
                        item_value=doc,
                    )
                )

    return plan


def get_training_plan_snowflake_impl(
    vn: Any,
    filter_databases: Union[List[str], None] = None,
    filter_schemas: Union[List[str], None] = None,
    include_information_schema: bool = False,
    use_historical_queries: bool = True,
) -> TrainingPlan:
    plan = TrainingPlan([])

    if vn.run_sql_is_set is False:
        raise ImproperlyConfigured("Please connect to a database first.")

    if use_historical_queries:
        try:
            print("Trying query history")
            df_history = vn.run_sql(
                """ select * from table(information_schema.query_history(result_limit => 5000)) order by start_time"""
            )

            df_history_filtered = df_history.query("ROWS_PRODUCED > 1")
            if filter_databases is not None:
                mask = (
                    df_history_filtered["QUERY_TEXT"]
                    .str.lower()
                    .apply(
                        lambda x: any(
                            s in x for s in [s.lower() for s in filter_databases]
                        )
                    )
                )
                df_history_filtered = df_history_filtered[mask]

            if filter_schemas is not None:
                mask = (
                    df_history_filtered["QUERY_TEXT"]
                    .str.lower()
                    .apply(
                        lambda x: any(
                            s in x for s in [s.lower() for s in filter_schemas]
                        )
                    )
                )
                df_history_filtered = df_history_filtered[mask]

            if len(df_history_filtered) > 10:
                df_history_filtered = df_history_filtered.sample(10)

            for query in df_history_filtered["QUERY_TEXT"].unique().tolist():
                plan._plan.append(
                    TrainingPlanItem(
                        item_type=TrainingPlanItem.ITEM_TYPE_SQL,
                        item_group="",
                        item_name=vn.generate_question(query),
                        item_value=query,
                    )
                )

        except Exception as e:
            print(e)

    databases = vn._get_databases()

    for database in databases:
        if filter_databases is not None and database not in filter_databases:
            continue

        try:
            df_tables = vn._get_information_schema_tables(database=database)

            print(f"Trying INFORMATION_SCHEMA.COLUMNS for {database}")
            df_columns = vn.run_sql(f"SELECT * FROM {database}.INFORMATION_SCHEMA.COLUMNS")

            for schema in df_tables["TABLE_SCHEMA"].unique().tolist():
                if filter_schemas is not None and schema not in filter_schemas:
                    continue

                if not include_information_schema and schema == "INFORMATION_SCHEMA":
                    continue

                df_columns_filtered_to_schema = df_columns.query(
                    f"TABLE_SCHEMA == '{schema}'"
                )

                try:
                    tables = df_columns_filtered_to_schema["TABLE_NAME"].unique().tolist()

                    for table in tables:
                        df_columns_filtered_to_table = df_columns_filtered_to_schema.query(
                            f"TABLE_NAME == '{table}'"
                        )
                        doc = (
                            f"The following columns are in the {table} table in the {database} database:\n\n"
                        )
                        doc += df_columns_filtered_to_table[
                            [
                                "TABLE_CATALOG",
                                "TABLE_SCHEMA",
                                "TABLE_NAME",
                                "COLUMN_NAME",
                                "DATA_TYPE",
                                "COMMENT",
                            ]
                        ].to_markdown()

                        plan._plan.append(
                            TrainingPlanItem(
                                item_type=TrainingPlanItem.ITEM_TYPE_IS,
                                item_group=f"{database}.{schema}",
                                item_name=table,
                                item_value=doc,
                            )
                        )

                except Exception as e:
                    print(e)
        except Exception as e:
            print(e)

    return plan
