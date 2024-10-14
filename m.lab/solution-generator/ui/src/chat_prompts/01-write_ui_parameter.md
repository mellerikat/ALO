# Write UI Parameter

<div align="right">Updated 2024.05.05</div><br />

In the experimental_plan.yaml file, you can set parameters that users can modify in the EdgeConductor UI. This allows the AI Solution developer to predefine essential parameters required for the project and clearly specify which parameters the AI Solution user can change. By setting up these parameters in the configuration file, users can easily adjust and experiment with the model by simply entering or selecting the necessary parameter values. The experimental_plan.yaml supports limited UI parameter types, such as Float, Integer, String, Single Selection, and Multi Selection, to enhance usability, reduce the potential for errors, and prevent users from mistakenly setting critical parameters incorrectly.
Once the AI model has been thoroughly tested and its performance verified in the development environment of the AI Solution, it can be registered and deployed directly to the operational stage on the Mellerikat platform using the register-ai-solution.ipynb Jupyter notebook. The UI parameters set by the AI Solution developer will also be automatically reflected in the EdgeConductor UI and shown to the user.

**Topics**
<!-- TOC ## Level 2 ~ 3 까지 -->
- [Declaring UI Parameters](#ui-parameter-선언)
- [Detailed Description of UI Parameters](#ui-parameter-상세-기술)
<!-- /TOC -->

<br/ >

---

## Declaring UI Parameters <a id="ui-parameter-선언"></a>
Write the parameters provided as a UI in Edge Conductor in experimental_plan.yaml.
First, select the items to be displayed in the UI from user_parameters and write the parameter names in ui_args.

```yaml
#experimental_plan.yaml

user_parameters:
    - train_pipeline:
        - step: input
          args:
            - input_path: train
              x_columns: [input_x0, input_x1, input_x2, input_x3]
			  y_column: label
          ui_args:
            - x_columns
            - y_column
```
Write detailed information for the parameters listed in ui_args in the ui_args_detail section of experimental_plan.yaml.

<br />

---

## Detailed Description of UI Parameters <a id="ui-parameter-상세-기술"></a>
 
```yaml
#experimental_plan.yaml

ui_args_detail:
    - train_pipeline:
        - step: input
          args:
              - name: x_columns
                description: TCR 모델링에 사용될 x columns를 ','로 구분하여 기입합니다. ex) x_column1, x_column2
                type: string
                default: ''
                range:
                  - 1
                  - 1000000

              - name: y_column
                description: TCR 모델링에 사용될 y column명을 기입합니다. ex) y_column
                type: string
                default: ''
                range:
                  - 1
                  - 1000000
```

You can choose from float, int, string (or string type list), single_selection, and multi_selection types for the type of UI args.
Write the required information for each type in the ui_args_detail section.

**_Note:_** Each AI Contents manual page lists the available UI Parameters and detailed information that can be used.

- float or int
    - Supports int and float types.
    - The range indicates the min and max value range.

    ```yaml
    - name: float_param
    description: this is param to input float
    type: float
    default:
        - 0.5
    range:
        - 0.0
        - 1.0
    ```

- string
    - Use when a string value needs to be entered.
	- The range indicates the character length limit.

    ```yaml
        - name: string_param
        description: this is param to input string
        type: string
        default:
            - "hello"
        range:
            - 5
            - 100
    ```

    - To support a list, use the string type.
        - If the user enters multiple values separated by commas (", ") in the string type parameter in the UI, the values are split and delivered as a list during training in AI Conductor.
            (e.g., "value1, value2, value3" --> \["value1", "value2", "value3"\])
        - **Warning** : If the user enters values like 1, 2, 3 in the string type parameter in the EdgeConductor UI, the entered values are delivered to ALO as \["1", "2", "3"\]. Therefore, if the values in the list need to be integers instead of strings, type conversion code should be written inside the Asset.

        ```yaml
        - name: string_param
        description: this is param to input string
        type: string
        default:
            - "x1, x2, x3,"
        range:
            - 5
            - 100
        ```

- single_selection
    - Use when one value needs to be selected from selectable values.

    ```yaml
    - name: single_selection_param
    description: this is param to input single selection
    type: single_selection
    selectable:
        - option1
        - option2
        - option3
    default:
        - option1
    ```

- multi_selection
    - Use when multiple values need to be selected from selectable values.

    ```yaml
    - name: multi_selection_param
    description: this is param to input multi selection
    type: multi_selection
    selectable:
        - option1
        - option2
        - option3
    default:
        - option1
        - option3
    ```
