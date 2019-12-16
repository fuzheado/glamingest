function button_copy() {
  let textarea = document.getElementById('quickstatement');
  textarea.select();
  document.execCommand('copy');
}
