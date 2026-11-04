package fx.service;

import fx.mapper.CustomerMapper;

public class CustomerService {
    private CustomerMapper customerMapper;

    public Object get(int id) {
        return customerMapper.getCustomer(id);         // L0 call_abstraction (no Java implementation)
    }
}
