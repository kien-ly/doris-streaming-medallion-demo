{% macro grant_roles() %}
  {% if execute %}
    {% do run_query("CREATE ROLE IF NOT EXISTS analytics_reader") %}
    {% do run_query("CREATE ROLE IF NOT EXISTS analytics_engineer") %}
    {% do run_query("GRANT SELECT_PRIV ON analytics.* TO ROLE analytics_reader") %}
    {% do run_query("GRANT SELECT_PRIV, LOAD_PRIV, ALTER_PRIV, CREATE_PRIV, DROP_PRIV ON dwh.* TO ROLE analytics_engineer") %}
    {% do run_query("GRANT SELECT_PRIV, LOAD_PRIV, ALTER_PRIV, CREATE_PRIV, DROP_PRIV ON analytics.* TO ROLE analytics_engineer") %}
  {% endif %}
{% endmacro %}

