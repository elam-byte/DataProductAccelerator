-- Routes dbt models to the correct medallion layer schema based on folder path.
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ node.fqn[-2] if node.fqn | length > 1 else target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
