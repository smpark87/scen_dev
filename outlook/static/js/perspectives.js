/* 선택 검증만 보조한다. 원천 데이터/가설/스냅샷은 서버에서 처리한다. */
const perspectiveForm = document.getElementById('perspective-form');
if (perspectiveForm) {
  const feedback = document.getElementById('selection-feedback');
  const choices = [...perspectiveForm.querySelectorAll('input[name="axes"]')];
  const refresh = () => {
    const count = choices.filter((choice) => choice.checked).length;
    feedback.textContent = count ? `${count} ${count === 1 ? 'axis' : 'axes'} selected.` : '';
  };
  choices.forEach((choice) => choice.addEventListener('change', refresh));
  perspectiveForm.addEventListener('submit', (event) => {
    if (!choices.some((choice) => choice.checked)) {
      event.preventDefault();
      feedback.textContent = 'Select at least one axis to save your perspective.';
      choices[0].focus();
    }
  });
}
