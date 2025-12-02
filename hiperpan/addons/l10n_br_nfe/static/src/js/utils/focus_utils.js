/** @odoo-module **/

/**
 * Utilitários para manipulação de foco em elementos do DOM.
 */

/**
 * Remove o foco do elemento atualmente focado criando um input temporário
 * invisível, focando nele e depois removendo-o. Isso é útil quando métodos
 * simples como blur() não funcionam devido ao comportamento de restauração
 * de foco de dialogs ou outros componentes.
 * 
 * @param {Object} options - Opções de configuração
 * @param {number} [options.delay=0] - Delay em ms antes de executar o steal
 * @param {number} [options.cleanupDelay=10] - Delay em ms antes de remover o input temporário
 * @returns {Promise<void>} Promise que resolve quando o foco foi removido
 */
export function stealFocus(options = {}) {
    const { delay = 0, cleanupDelay = 10 } = options;
    
    return new Promise((resolve) => {
        setTimeout(() => {
            // Cria um input invisível temporário para roubar o foco
            const tempInput = document.createElement("input");
            tempInput.style.position = "absolute";
            tempInput.style.left = "-9999px";
            tempInput.style.top = "-9999px";
            tempInput.style.opacity = "0";
            tempInput.style.pointerEvents = "none";
            tempInput.setAttribute("aria-hidden", "true");
            tempInput.setAttribute("tabindex", "-1");
            document.body.appendChild(tempInput);
            tempInput.focus();
            
            // Remove o input após roubar o foco
            setTimeout(() => {
                tempInput.blur();
                if (tempInput.parentNode) {
                    tempInput.parentNode.removeChild(tempInput);
                }
                resolve();
            }, cleanupDelay);
        }, delay);
    });
}

/**
 * Remove o foco do elemento atualmente focado de forma síncrona.
 * Versão simplificada sem Promise para casos onde não é necessário aguardar.
 */
export function stealFocusSync() {
    const tempInput = document.createElement("input");
    tempInput.style.position = "absolute";
    tempInput.style.left = "-9999px";
    tempInput.style.top = "-9999px";
    tempInput.style.opacity = "0";
    tempInput.style.pointerEvents = "none";
    tempInput.setAttribute("aria-hidden", "true");
    tempInput.setAttribute("tabindex", "-1");
    document.body.appendChild(tempInput);
    tempInput.focus();
    
    setTimeout(() => {
        tempInput.blur();
        if (tempInput.parentNode) {
            tempInput.parentNode.removeChild(tempInput);
        }
    }, 10);
}

