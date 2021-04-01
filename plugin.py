
import os
import re
import subprocess
import threading

import sublime, sublime_plugin


RE_TEST = re.compile(r'^func (Test[a-zA-Z0-9]+)\(t \*testing\.T\) {')


class GoTestWorker(threading.Thread):
  def __init__(self, window, folder, test_name):
    self.window = window
    self.folder = folder
    self.test_name = test_name
    threading.Thread.__init__(self)

  def run(self):
    output_view = self.window.create_output_panel('go_test')

    cmd = [
      '/usr/local/go/bin/go',
      'test',
      '-v',
      '-timeout', '30s',
      '-count', '1',
      '-run', '^' + self.test_name + '$',
      '.',
    ]
    output_view.run_command('append', {'characters': '> Command: %s\n' % subprocess.list2cmdline(cmd)})

    self.window.run_command('show_panel', {'panel': 'output.go_test'})

    p = subprocess.Popen(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.folder)
    while True:
      output = p.stdout.readline()
      if output == b'' and p.poll() is not None:
        break
      if output:
        output_view.run_command('append', {'characters': output.decode('utf-8')})
 

class GoUtilsRunTestUnderCursorCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    window = self.view.window()
    
    folder, _ = os.path.split(self.view.file_name())

    # Save the file to have the new test on disk.
    window.run_command('save')

    # Search the nearest test name.
    line = self.view.line(self.view.sel()[0].begin())
    while True:
      match = RE_TEST.match(self.view.substr(line))
      if match:
        worker = GoTestWorker(window, folder, match.group(1))
        worker.start()
        break

      if line.begin() == 0:
        sublime.error_message('Nearest Go Test not found')
        return

      line = self.view.line(sublime.Region(line.begin() - 1, line.begin() - 1))


class GoUtilsGoimportsCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    folder, _ = os.path.split(self.view.file_name())

    selection = sublime.Region(0, self.view.size())
    content = self.view.substr(selection)

    modname = subprocess.run([
      '/usr/local/go/bin/go',
      'list',
      '-f', '{{.Module}}',
      '.',
    ], stdout=subprocess.PIPE, universal_newlines=True, cwd=folder)

    gopath = subprocess.run([
      '/usr/local/go/bin/go',
      'env',
      'GOPATH',
    ], stdout=subprocess.PIPE, universal_newlines=True)
    env = os.environ.copy()
    env["PATH"] = ':'.join([env["PATH"], '/usr/local/go/bin', os.path.join(gopath.stdout.strip(), 'bin')])
    p = subprocess.Popen([
      'goimports',
      '-srcdir', folder,
      '-local', modname.stdout.strip(),
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=folder, env=env)
    p.stdin.write(bytes(content, 'utf8'))
    p.stdin.close()
    p.wait()
        
    error = p.stderr.read().decode('utf8')
    if error != '':
      overview = error.split('\n')[0]
      if '<standard input>' in overview:
        overview = 'L' + overview.split('<standard input>:')[1]
      self.view.set_status('go', 'ERROR: ' + overview)
    else:
      self.view.set_status('go', '')
      self.view.replace(edit, selection, p.stdout.read().decode('utf8'))


class GoImportsListener(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if view.settings().get('syntax') != 'Packages/Go/Go.sublime-syntax':
      return

    view.run_command('go_utils_goimports')
