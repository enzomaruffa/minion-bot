
cpf_nove_digitos = "109609339"

digito_10 = (10 * int(cpf_nove_digitos[0]) + 9 * int(cpf_nove_digitos[1]) + 8 * int(cpf_nove_digitos[2]) + 7 * int(cpf_nove_digitos[3]) + 6 * int(cpf_nove_digitos[4]) + 5 * int(cpf_nove_digitos[5]) + 4 * int(cpf_nove_digitos[6]) + 3 * int(cpf_nove_digitos[7]) + 2 * int(cpf_nove_digitos[8])) % 11

if digito_10 == 10:
    digito_10 = 0

print("Digito 10:", digito_10)

digito_11 = (11 * int(cpf_nove_digitos[0]) + 10 * int(cpf_nove_digitos[1]) + 9 * int(cpf_nove_digitos[2]) + 8 * int(cpf_nove_digitos[3]) + 7 * int(cpf_nove_digitos[4]) + 6 * int(cpf_nove_digitos[5]) + 5 * int(cpf_nove_digitos[6]) + 4 * int(cpf_nove_digitos[7]) + 3 * int(cpf_nove_digitos[8]) + 2 * digito_10) % 11

if digito_11 < 2:
    digito_11 = 0

print("Digito 11:", digito_11)

print("CPF completo:", cpf_nove_digitos + str(digito_10) + str(digito_11))