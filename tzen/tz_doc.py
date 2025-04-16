from __future__ import annotations

from .tz_test import TZTest
import os
import jinja2
import pathlib
import yaml

CUSTOM_BACKEND = None
MKDOCS_YAML_PRJ_TEMPLATE = """ # MkDocs configuration template for test documentation

site_name: {{ site_name | default('Test Documentation') }}
site_description: {{ site_description | default('Documentation for TZTest test suite') }}
docs_dir: {{ docs_dir | default('docs') }}
site_dir: {{ site_dir | default('site') }}

nav:
  - Home: index.md
  {% for module_name, module in modules.items() %}
  - {{ module_name | capitalize }}:
      - Overview: {{ module_name | lower }}/index.md
      {% for test in module.tests %}
      - {{ test.__name__ }}: {{ module_name | lower }}/{{ test.__name__ | lower }}.md
      {% endfor %}
  
  {% endfor %}

theme:
  name: {{ theme | default('material') }}
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - search.highlight

plugins:
  - search
  {% if extra_plugins %}
  {% for plugin in extra_plugins %}
  - {{ plugin }}
  {% endfor %}
  {% endif %}

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - attr_list
  - md_in_html

"""
MKDOCS_TEST_DESCRIPTION_TEMPLATE = """# {{ test_name }}
{% if test_class.doc %}
{{ test_class.doc }}
{% else %}
No documentation available for this test.
{% endif %}

## Overview

This test is defined in the `{{ module_name }}` module.


{% if test_class.steps %}
## Test Steps

{% for step in test_class.steps %}
### {{ step.name }}

{% if step.doc %}
{{ step.doc }}
{% else %}
No documentation available for this step.
{% endif %}
{% endfor %}
{% endif %}
"""
MKDOCS_MODULE_INDEX_TEMPLATE = """# {{ module_name | default(module.name, true) }} Module

{% if module.description %}
{{ module.description }}
{% else %}
No description available for this module.
{% endif %}

## Module Information

| Property | Value |
| -------- | ----- |
{% if module.version %}| Version | {{ module.version }} |{% endif %}
{% if module.author %}| Author | {% if module.author.name %}{{ module.author.name }}{% if module.author.email %} ({{ module.author.email }}){% endif %}{% else %}{{ module.author }}{% endif %} |{% endif %}

{% if module.dependencies and module.dependencies|length > 0 %}
## Dependencies

{% for dependency in module.dependencies %}
- {{ dependency }}
{% endfor %}
{% endif %}
"""

class TZDoc:
    """
    Class to handle the documentation of the Tzen library.
    This class can be overridden to provide custom documentation backends.
    The default backend is the TZDoc class itself.
    This class produces a mkdocs like project with the documentation of the tests.
    It takes as input a dictionary representing the structure of the test environment in a tree-like format. Root folder is considered the root of the test documentation. 
    If an __init__.py file is present in the folder, its docstring will be exctrated and used as a test container.
    """

    def __init__(self, test_environment, output_folder):
        """
        Initialize the TZDoc class.
        """
        self.test_environment = test_environment
        self.output_folder = output_folder
    
    
    def build_documentation(self):
        """
        Build the documentation from the test environment.
    
        Args:
            test_environment (dict): The test environment.
            output_folder (str): The output folder.
        """
        # Create the output folder if it doesn't exist
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Sets the project path to the output folder        
        project_path = self.output_folder
        docs_dir = os.path.join(project_path, "docs")
        
        # Create docs directory for each module
        os.makedirs(docs_dir, exist_ok=True)
            
        self.build_project_tree(docs_dir)
        
        # For each module, create a directory and a placeholder file
        for module_name, module in self.test_environment.items():
            
            if module_name != "__init__":
                os.makedirs(os.path.join(docs_dir, module["path"]), exist_ok=True)

            # If it's an init, create a Index file for that module
            if module_name == "__init__":
                self.build_module_index(module["module"], os.path.join(docs_dir, os.path.dirname(module["path"]), "index.md"))

            else:
                for test in module["tests"]:
                    # Create a file for each test case
                    test_name = test.__name__.lower()
                    test_file_path = os.path.join(docs_dir, module["path"], f"{test_name}.md")
                    
                    # Create the documentation for the test case
                    self.build_testcase_documentation(test, test_file_path)
                
    def build_project_tree(self, docs_dir:str) -> None:
        
        # Set up Jinja environment
        template_env = jinja2.Environment(autoescape=False)
        mkdocs_template = template_env.from_string(MKDOCS_YAML_PRJ_TEMPLATE)
        
        # Render and write mkdocs.yml
        rendered_template = mkdocs_template.render(
            site_name="Test Documentation",
            modules=self.test_environment,
            docs_dir=docs_dir
        )
        
        with open(os.path.join(self.output_folder, "mkdocs.yml"), "w") as f:
            f.write(rendered_template)
    
    def build_module_index(self, module, output_file:str):
        """ Creates the output file.md in order to describe a module. Takes as parameter a module object and a file path.
        Parses the module docstring and creates a dictionary based on the implementation on the module_doc_to_dict"""
        
        module_dict = self.module_doc_to_dict(module.__doc__)
        # Set up Jinja environment
        template_env = jinja2.Environment(autoescape=False)
        module_template = template_env.from_string(MKDOCS_MODULE_INDEX_TEMPLATE)
        # Render and write mkdocs.yml
        rendered_template = module_template.render(
            module=module_dict
        )
        with open(output_file, "w") as f:
            f.write(rendered_template)
            
    def build_testcase_documentation(self, test_class:TZTest, output_file:str):
        pass
    
    def testclass_doc_to_dict(self, test_class_doc:str) -> dict:
        """
        Convert a test class docstring to a dictionary.
    
        Args:
            test_class_doc (str): The test class docstring to convert.
    
        Returns:
            dict: The dictionary representation of the test class docstring.
        """
        return yaml.safe_load(test_class_doc)
    
    def module_doc_to_dict(self, module_doc:str) -> dict:
        """
        Convert a module docstring to a dictionary.
    
        Args:
            module_doc (str): The module docstring to convert.
    
        Returns:
            dict: The dictionary representation of the module docstring.
        """
        return yaml.safe_load(module_doc)
    
    def __init_subclass__(cls):
        CUSTOM_BACKEND = cls
        




def build_documentation(test_environment:dict, output_folder:str):
    """
    Build the documentation from the test environment.
    
    Args:
        test_environment (dict): The test environment.
        output_folder (str): The output folder.
    """
    
    
    if CUSTOM_BACKEND is not None:
        # Use the custom backend if available
        doc_backend = CUSTOM_BACKEND(test_environment, output_folder)
    else:
        # Use the default backend
        doc_backend = TZDoc(test_environment, output_folder)
            
    doc_backend.build_documentation()
    
    # test_template = template_env.from_string(MKDOCS_TEST_DESCRIPTION_TEMPLATE)
            
    
    # # Create index.md in the docs directory
    # with open(os.path.join(docs_dir, "index.md"), "w") as f:
    #     f.write("# Test Documentation\n\nWelcome to the test documentation.\n")
    
    # # Create directory and placeholder files for each module
    # for module_name, module_data in modules.items():
    #     module_dir = os.path.join(docs_dir, module_name.lower())
    #     os.makedirs(module_dir, exist_ok=True)
        
    #     # Create module index file
    #     with open(os.path.join(module_dir, "index.md"), "w") as f:
    #         f.write(f"# {module_name.capitalize()} Module\n\n")
    #         f.write(f"This section contains tests for the {module_name} module.\n")
        
    #     # Create test documentation files
    #     for test_name in module_data["tests"]:
    #         test_info = test_environment.get(test_name, {})
            
    #         # Extract test class information
    #         test_class_info = {
    #             "name": test_name,
    #             "steps": []
    #         }
            
    #         test_class_info.update(self.testclass_doc_to_dict(test_info.get('test_class').__doc__))
            
    #         # Extract steps if available
    #         if 'steps' in test_info:
    #             for step_name, step_info in test_info.get('steps', {}).items():
    #                 test_class_info["steps"].append({
    #                     "name": step_name,
    #                     "doc": step_info.get('doc', '')
    #                 })
            
    #         # Extract fixtures if available
    #         fixtures = []
    #         if 'fixtures' in test_info:
    #             for fixture_name, fixture_info in test_info.get('fixtures', {}).items():
    #                 fixtures.append({
    #                     "name": fixture_name,
    #                     "doc": fixture_info.get('doc', '')
    #                 })
            
    #         # Render test documentation
    #         rendered_test_doc = test_template.render(
    #             test_name=test_name,
    #             module_name=module_name,
    #             test_class=test_class_info,
    #             fixtures=fixtures
    #         )
            
    #         # Write test documentation file
    #         with open(os.path.join(module_dir, f"{test_name.lower()}.md"), "w") as f:
    #             f.write(rendered_test_doc)
