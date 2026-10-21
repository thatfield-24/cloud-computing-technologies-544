# Header
In both cases the Boot/npm install time took up roughly 20s while the health check occured for an additional 20s. This means that the remaning ~roughly 25 seconds was on detection and +- a few seconds in the other categories. This is mostly equal but the installation could begin to take longer on largre applications.


Output of ls -a lab05 (or a screenshot) showing the layout from Part 0 and section 4.

Screenshot of pytest showing 19 passed.
# Currently only 12 are passing: test_stack_with_moto.py is not running properly


Screenshot of one "break it on purpose" experiment: the changed line and the failing test message.
Screenshot of python create_stack.py completing, with both URLs.
Screenshot of pytest -m integration -v with all 14 tests passing.
Output of pytest -m chaos -s for both tiers, and the same run failing after you tightened the SLO.
Screenshot of python delete_stack.py completing, and a second run completing with no errors.
One paragraph on what moto proved, what it could not, and which tests cover the gap.
One paragraph comparing ignore_errors("EntityAlreadyExists") with 2>/dev/null || true .
Your answer to Challenge 5.
Pick one place where the bash version was shorter than the Python version. Write two sentences on what the extra
Python lines bought you.


![Lab05 Setup](images/lab05_setup.png.png)

