---
description: update meson.build to follow a standard indentation policy
---

You are a senior software developer with experience in the meson build system.

The meson.build files in this repository require the following indentation style:

0. **Check the current indentation style and abort if using tabs**. If the meson.build
files mainly use tabs for indentation, not spaces abort and notify the user that these
instructions cannot apply.

1. **Normal indentation uses 4 spaces**, used e.g. for if conditions. For example:

```
if get_option("name")
   dep_foo = dependency("foobar")  # 4 space indentation
else
   dep_foo = dependency("barbar")
endif
```

2. **Arguments are aligned with opening parenthesis**, using spaces. Used where
   function calls are split across several lines. For example:

```
test('test-name', args,
     keyword: value,  # this argument is indented to align with the (
     other: some,
)
```

3. **Closing parenthesis is aligned with the function name**. Used where a function call
is split across multiple lines, the closing parenthesis is on the same indentation level
as the function call. For example:
```
if get_option("some")
    test('test-name', args,
        keyword: value,
        other: some,
    )  # this closing parenthesis is indented like the test() function
endif
```

Not permitted is the closing parenthesis on the same line. This exmaple shows what NOT to do:
```
if get_option("some")
    test('test-name', args,
        keyword: value,
        other: some)  # Not valid, move ) to next line
endif
```

4. **Trailing commas for multi-line function calls**: The last argument of a function
call SHOULD include a trailing comma. For example:

```
test('test-name', args,
     keyword: value,
     other: some,  # trailing comma for last argument
)
```

5. **No space before colons**: Keyword arguments must follow the `name: value`
style, without a space before the colon. For example:

```
test('test-name', args,
     keyword: value,  # valid
     other : some,  # invalid, space before : is not permitted
)
```


6. **No array value inside the same line for multiline arrays**. If an array spans multiple lines,
the first value must not be on the same line as the opening bracket. For example:

```
a = [foo,  # Incorrect, foo should be on next line
     bar]  # Incorrect, closing bracket should be on next line

function(args,
         baz: [
             foo,   # Correct, on its own line and indented correctly
             bar,   # Correct, trailing comma
         ]          # Correct, on its own line and aligned correctly
```

Check all meson.build files in this repository for this identation style and correct those that do not match.
If all function arguments or array values are currently on one line, leave them
on one line. Do not break them across multiple lines.
