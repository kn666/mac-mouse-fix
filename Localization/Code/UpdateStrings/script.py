
"""

This script helps to keep .strings files in sync with source code and IB files.
It's a replacement for bartycrouch.

Manual testing steps:

- [ ] StateOfLocalization doesn't change after this updates everything.
- [x] Multiline values like addField hint (N7H-9j-DIr.title) don't duplicate or anything
- [x] Insert key in source file
    - Test both IB and code source file (insert in code using NSLocalizedString)
    -> Result: String shows up in .strings file with correct comment and empty value. (Localizable.strings is for source code)
- [x] Delete autogenerated comment in .strings file, Add inline comment, add value, reorder
    - Test both IB and code source file
    -> Result: Inline comment and value are preserved. Order and autogenerated comment are restored. (It's important to preserve inline comments for our !IS_OK flags)
    ->      Currently 03.01.2024 this sometimes deletes surrounding values. But I can't reproduce this despite best efforts. Very strange.
- [x] Add superfluous kv-pair, add comment above
    -> Result: Superfluous kv-pair is moved to end of file, comment is preserved
"""

#
# Native imports
#

import sys
import os
from pprint import pprint
import argparse

import cProfile

#
# Import functions from ../Shared folder
#

code_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if code_dir not in sys.path:
    sys.path.append(code_dir)
from Shared import shared

#
# Constants
#

temp_folder = './update_comments_temp'

#
# Main
#

def main():
    
    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument('--wet_run', required=False, action='store_true', help="Provide this arg to actually modify files. Otherwise it will just log what it would do.", default=False)
    args = parser.parse_args()
    
    # Constants & stuff
    repo_root = os.getcwd()
    assert os.path.basename(repo_root) == 'mac-mouse-fix', "Run this script from the 'mac-mouse-fix' repo folder."
    
    # Create temp dir
    shared.runCLT(f"mkdir -p {temp_folder}")
    
    # Find files
    ib_files = shared.find_localization_files(repo_root, None, ['IB'])
    strings_files = shared.find_localization_files(repo_root, None, ['strings'])
    
    # Update .strings files
    update_strings_files(ib_files, args.wet_run, 'IB')
    update_strings_files(strings_files, args.wet_run, 'sourcecode')
    
    # Debug
    # pprint(ib_files)
    # pprint(strings_files)
    
    # Clean up
    shared.runCLT(f"rm -R ./{temp_folder}")
    
    if not args.wet_run:
        print("This is a dry run. No files are actually changed even if the logs say so.")
    
    
#
# Update .strings files
#

def update_strings_files(files, wet_run, type):
    
    """
    (if type == 'sourcecode')   Update .strings files to match source code files which they translate
    (if type == 'IB')           Update .strings files to match .xib/.storyboard files which they translate
    
    Discussion: 
    - In update_ib_comments we don't update development language files - because there are none, since development language strings are directly inside the ib files.
      But in this function, we also update en.lproj/Localizable.strings. Maybe we should've specified development language values directly in the source code using `NSLocalizedStringWithDefaultValue` instead of inside en.lproj. That way we wouldn't need en.lproj at all.
      Not sure anymore why we chose to do it with en.lproj instead of all source code for English. But either way, I don't think it's worth it to change now.
    Note:
    """
    
    print(f"\nUpdating strings files type {type}...")
    
    assert type in ['sourcecode', 'IB']
    if type == 'sourcecode': assert len(files) == 1, "There should only be one base .strings file - Localizable.strings"
    
    for file_dict in files:
    
        generated_content = ''
        if type == 'sourcecode':
            source_code_files = shared.find_files_with_extensions(['m','c','cp','mm','swift'], ['env/', 'venv/', 'iOS-Polynomial-Regression-master/', './Test/'])
            source_code_files_str = ' '.join(map(lambda p: p.replace(' ', r'\ '), source_code_files))
            shared.runCLT(f"xcrun extractLocStrings {source_code_files_str} -SwiftUI -o ./{temp_folder}", exec='/bin/zsh')
            generated_path = f"{temp_folder}/Localizable.strings"
            generated_content = shared.read_file(generated_path, 'utf-16')
        elif type == 'IB':
            base_file_path = file_dict['base']
            generated_path = shared.extract_strings_from_IB_file_to_temp_file(base_file_path)
            generated_content = shared.read_tempfile(generated_path)
        else: 
            assert False
        
        strings_file_paths = list(file_dict['translations'].keys())
        if type == 'sourcecode':
            strings_file_paths.append(file_dict['base'])
        
        modss = []
        
        for path in strings_file_paths:
            
            content = shared.read_file(path, 'utf-8')
            new_content, mods, ordered_keys = update_strings_file_content(content, generated_content)
            
            if wet_run and new_content != content:
                shared.write_file(path, new_content)
            
            modss.append({'path': path, 'mods': mods, 'ordered_keys': ordered_keys})
        
        log_modifications(modss)
        

#
# Debug helper
#

def log_modifications(modss):
    
    """
    Notes: 
    - Not sure if show_line_numbers in shared.get_diff_string is useful. the line number isn't the line number in the source file 
        but instead it's the position of the kv-pair in the list of kv-pairs in the source file.
    """
    
    result = ''
    
    for mods in modss:
        
        path_result = ''
        
        keys_before = '\n'.join(mods['ordered_keys']['before'])
        keys_after = '\n'.join(mods['ordered_keys']['after'])
        keys_diff = shared.get_diff_string(keys_before, keys_after, filter_unchanged_lines=False, show_line_numbers=True)
        
        if len(keys_diff) > 0:
            if False: # This sucks. Just use git diff.
                path_result += f"\n\n    Key order diff:\n{shared.indent(keys_diff, 8)}"
            else: 
                path_result += f"\\n\n    The order of keys seems to have changed. (I think - this might be broken)"
                
    

        for mod in sorted(mods['mods'], key=lambda x: x['modtype'], reverse=True):
            
            key = mod['key']
            modtype = mod['modtype']
            if modtype == 'comment':
                
                b = mod['before'].strip()
                a = mod['after'].strip()
                
                if a == b:
                    path_result += f"\n\n    {key}'s comment whitespace changed"    
                else:
                    a = shared.indent(a, 8)
                    b = shared.indent(b, 8)
                    
                    path_result += f"\n\n    {key} comment changed:\n{b}\n        ->\n{a}"
                
            elif modtype == 'insert':
                value = shared.indent(mod['value'], 8)
                path_result += f"\n\n    {key} was inserted:\n{value}"
                
            else: assert False
        
        if len(path_result) > 0:
            result += f"\n\n{mods['path']} was modified:{path_result}"
        else:
            result += f"\n{mods['path']} was not modified"
    
    if len(result) > 0:
        print(result)
            
    
    
#
# String parse & modify
#

def update_strings_file_content(content, generated_content):
    
    """
    At the time of writing:
    - Copy over all comments from `generated_content` to `content`
    - Insert kv-pair + comment from `generated_content` into `content` - if the kv-pair is not found in `content`
    - Reorder kv-pairs in `content` to match `generated_content`
    """
    
    # Parse both contents
    parse = parse_strings_file_content(content)
    generated_parse = parse_strings_file_content(generated_content, remove_value=True) # `extractLocStrings` sets all values to the key for some reason, so we remove them.
    
    # Record modifications for diagnositics
    mods = []
    
    # Replace comments 
    #   (And insert missing kv-pairs, too, to be able to add comments)
    for key in generated_parse.keys():
        
        is_missing = key not in parse
        
        p = None if is_missing else parse[key]
        g = generated_parse[key]
        
        if is_missing:
            
            parse[key] = g
            mods.append({'key': key, 'modtype': 'insert', 'value': g['comment'] + g['line']})
            
        else:
            if p['comment'] != g['comment']:
                mods.append({'key': key, 'modtype': 'comment', 'before': p['comment'], 'after': g['comment']})
                p['comment'] = g['comment']
    
    # Validate parse
    
    all_keys = set(parse.keys()).union(set(generated_parse.keys())) # For debugging
    for l in all_keys:
        l_comment = parse[l]['comment']
        for k in all_keys: # Idea: you could also check if the key appears in single\double quotes, or after linebreak to increase confidence that something is broken.
            assert f"{k}" not in l_comment, f"The key {k} appears in the comment for key {l}. Something is probably broken in the parsing code. Not proceeding. Comment:\n\n{parse[l]['comment']}\n\n"
    
    # Reassemple parse into updated content
    
    new_content = ''
    
    # Get new keys in order
    # Notes: 
    # - First we attach kv-pairs that also occur in generated_content
    #       dict.keys() are in insertion order in python. Therefore, this should synchronize the order of kv-pairs in the new_content with the generated_content
    # - Then, we attach unused kv-pairs at the end. 
    #       Why not just delete them?
    
    new_keys = list(generated_parse.keys())
    superfluous_keys = [k for k in parse.keys() if k not in generated_parse.keys()]
    new_keys += superfluous_keys
    
    # Attach
    for k in new_keys:
        new_content += parse[k]['comment']
        new_content += parse[k]['line']
        
    # Analyze reordering
    ordered_keys = {
        'before': parse.keys(),
        'after': list(generated_parse.keys()) + superfluous_keys
    }
    
    # Return
    return new_content, mods, ordered_keys
    
    

def parse_strings_file_content(content, remove_value=False):
    
    """
    
    Parse a .strings file into this structure:      (Should also work on .js translation files, but untested)
    {
        "<translation_key>": {
            "comment": "<comment_string>",
            "line": "<translation_key_value_string>",
        },
        ...
    }
    
    Notes:
    - See shared.strings_file_regex() for context.
    """
    
    result = {}
    
    regex = shared.strings_file_regex()
    
    
    #
    # Approach 1: Line-based approach
    #
    
    """
    Notes:
    - On the line-based approach vs match-based approach:
        - line-based approach:
            - goes through the text line-by line, and applies the regex to each line.
            - That makes for simple code, and it allows us to verify that the .strings file has the correct format, instead of doing weird stuff like the match-based approach.
            - We used splitlines(True) to iterate lines, but this didn't work, because the strings sometimes contain the character 'LINE SEPARATOR' (U+2028) if you enter a linebreak in IB, and splitlines splits at those characters. (Example for this is the '+' field hint.)
        - match-based approach:
            - The match-based applies the regext for finding kv-pairs to the whole string, and then iterates through the matches.
            - This works fine, butttt if you forget to put a semicolon at the end, then it will consider the whole kv-pair part of a comment, and will simply delete it.
                This has happened to me a few times when I was tired and I HATE this behaviour. That's why we're going back to the line-based approach with some additional checks to make sure everything is well-formatted.
    - Somehow we seem to be replacing consecutive blank lines before and after comments with single blank lines in the output of the script. 
        That's nice, but I don't understand why it's happending. Might be coming from this function. Edit: It think it's just because we replace the comments and the comments from the generated content don't have double line breaks.
    """
    
    last_key = ''
    acc_comment = ''

    for line in content.splitlines(True): # `True` preserves linebreaks, so that we can easily stitch everything together exactly as it was.

        match = regex.match(line)

        if match:

            key = match.group(2)
            if remove_value:
                value_start = match.start(3)
                value_end = match.end(3)
                result_line = line[:value_start] + line[value_end:]
            else:
                result_line = line

            result[key] = { "line": result_line, "comment": acc_comment }
            acc_comment = ''

            last_key = key
        else:
            acc_comment += line 

    post_comment = acc_comment
    assert len(post_comment.strip()) == 0, f"There's content under the last key {last_key}. Don't know what to do with that. Pls remove."
    
    return result
    
    #
    # Approach 2: Match-based
    #
    
    last_match = None
    last_key = ''
    
    matches = list(regex.finditer(content))
    
    for match in matches:
        
        comment_start = last_match.end(0) if last_match else 0
        comment_end = match.start(0)
        comment = content[comment_start:comment_end]
        
        line_start = match.start(0)
        line_end = match.end(0)
        line = match.group(0)
        
        key = match.group(2)
        
        result_line = ''
        if remove_value:
            value_start = match.start(3)
            value_end = match.end(3)
            result_line = content[line_start:value_start] + content[value_end:line_end]
        else:
            result_line = line
        
        assert key not in result, f"There's a duplicate key {key}"
        result[key] = { "line": result_line, "comment": comment }
        
        last_key = key
        last_match = match
        
    last_match = matches[-1]
    assert len(content.rstrip()) == last_match.end(0), f"There's content under the last key {last_key}. Don't know what to do with that. Pls remove."
    
    
    return result

#
# Call main
#

if __name__ == "__main__": 
    # cProfile.run('main()')
    main()
    
    
